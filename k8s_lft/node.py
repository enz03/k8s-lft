from kubernetes import client, config
from kubernetes.stream import stream
from k8s_lft.watch import K8sWatcher
import subprocess
import re
import time
import json
import gc


# Brief: Node in a Kubernetes cluster
# This class represents a node (pod) in a network topology.
# It provides methods to create, manage, and interact with the pod,
# including networking capabilities such as connecting to other nodes
# via veth pairs, setting IP addresses, and managing routes.
class K8sNode:
    def __init__(self, nodeName, image="nicolaka/netshoot", cpu="500m", memory="512Mi", app="k8s-node", namespace="default", privileged=True):
        self.nodeName = f"{nodeName}-0"
        self.image = image
        self.privileged = privileged
        self.api = None
        self.app = app
        self.cpu = cpu
        self.memory = memory
        self.namespace = namespace
        self._generateKubeconfig("kubeconfig")
        config.load_kube_config(config_file="kubeconfig")
        topology_watcher=K8sWatcher(namespace="default", label_selector="app=k8s-node")
        topology_watcher.registerNode(self)
        self.api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()

    # Brief: Instantiate the node (pod) in Kubernetes
    # Params:
    #   **kwargs: Additional keyword arguments for instantiation (not used here, but can be extended)
    # Returns:
    #   None
    def instantiate(self):
        ss_manifest  = self._buildStatefulSetManifest()
        self.apps_api.create_namespaced_stateful_set(namespace=self.namespace, body=ss_manifest)
        self._waitUntilReady()
            


    # Brief: Connect this node to another node using a veth pair
    # Params:
    #   string other: Another K8sNode instance to connect to
    #   string interface_name: Name of the interface in this node
    #   string peer_interface_name: Name of the interface in the other node
    # Returns:
    #   None
    def connect(self, other: "K8sNode | str", interface_name: str, peer_interface_name: str, reconnect: bool = False):
        if isinstance(other, str):
            peer_name = other
            pid2 = self._getPodpid(peer_name) 

        elif isinstance(other, K8sNode):
            peer_node = other
            peer_name = other.nodeName
            pid2 = other._getPodpid()
            other._append_operation({
                 "op": "connect",
                 "peer": self.nodeName,
                 "interface_name": peer_interface_name,
                 "peer_interface_name": interface_name
            })

        else:
            raise TypeError("Parâmetro 'other' deve ser um str (nome) ou K8sNode")
        
        pid1 = self._getPodpid()


        print(f"Conectando {self.nodeName} (PID {pid1}) <--> {peer_name} (PID {pid2})")

        # # Clean up old interfaces if they exist
        # subprocess.run(f"sudo ip link delete {interface_name}", shell=True, stderr=subprocess.DEVNULL)
        # subprocess.run(f"sudo ip link delete {peer_interface_name}", shell=True, stderr=subprocess.DEVNULL)
        # Clean up old interfaces (try in all possible namespaces)
        for iface, pid in [(interface_name, pid1), (peer_interface_name, pid2)]:
            # Tenta deletar no namespace raiz
            subprocess.run(f"sudo ip link delete {iface}", shell=True, stderr=subprocess.DEVNULL)

            # Tenta deletar dentro do namespace do pod
            subprocess.run(f"sudo nsenter -t {pid} -n ip link delete {iface}", shell=True, stderr=subprocess.DEVNULL)


        # Create new veth pair
        subprocess.run(f"sudo ip link add {interface_name} type veth peer name {peer_interface_name}", shell=True, check=True)

        # Move interfaces to the respective namespaces
        subprocess.run(f"sudo ip link set {interface_name} netns {pid1}", shell=True, check=True)
        subprocess.run(f"sudo ip link set {peer_interface_name} netns {pid2}", shell=True, check=True)

        # Bring up the interfaces in their respective namespaces
        subprocess.run(f"sudo nsenter -t {pid1} -n ip link set {interface_name} up", shell=True, check=True)
        subprocess.run(f"sudo nsenter -t {pid2} -n ip link set {peer_interface_name} up", shell=True, check=True)

        if hasattr(self, '_connectInterface'):
            self._connectInterface(interface_name)
        if hasattr(other, '_connectInterface'):
            other._connectInterface(peer_interface_name)


        if not reconnect:
            # insert into statefulset logs, in case this pod crashes
            self._append_operation({
                "op": "connect",
                "peer": peer_name,
                "interface_name": interface_name,
                "peer_interface_name": peer_interface_name
            })


    # Brief: Set IP address on a specific interface inside the pod
    # Params:
    #   string ip: IP address to set
    #   int mask: Subnet mask (CIDR notation)
    #   string interface: Interface name to set the IP on
    # Returns:
    #   None
    def setIp(self, ip: str, mask: int, interface: str, reconnect: bool = False):
        if not reconnect:
            self._append_operation({
                "op": "setIp",
                "ip": ip,
                "mask": mask,
                "interface": interface
            })
        self.run(f"ip addr add {ip}/{mask} dev {interface}")
        self.run(f"ip link set {interface} up")
        print(f"[INFO] {self.nodeName} com ip {ip} na iface {interface}")
        


    # Brief: Run a command inside the pod
    # Params:
    #   string command: Command to run (string)
    # Returns:
    #   Command output (string)
    def run(self, command: str):
        exec_command = ["/bin/bash", "-c", command]
        return stream(self.api.connect_get_namespaced_pod_exec,
                      self.nodeName, "default",
                      command=exec_command,
                      stderr=True, stdin=False,
                      stdout=True, tty=False)


    # Brief: Delete the pod from Kubernetes
    # Params:
    #   None
    # Returns:
    #   None
    def delete(self):
        try:
            self.api.delete_namespaced_pod(name=self.nodeName, namespace="default")
        except Exception as e:
            print(f"Error deleting pod {self.nodeName}: {e}")


    # Brief: Get the PID of the pod's main container
    # Params:
    #   None
    # Returns:
    #   string PID 
    def _getPodpid(self, pod_name: str = None) -> str:
        if (pod_name is None):
            pod_name = self.nodeName

        pod = self.api.read_namespaced_pod(name=pod_name, namespace=self.namespace)
        container_statuses = pod.status.container_statuses
        if not container_statuses:
            raise RuntimeError(f"No container status found for pod {pod_name}")

        full_container_id = container_statuses[0].container_id  # Format: "containerd://<id>"
        match = re.match(r"containerd://([a-f0-9]+)", full_container_id)
        if not match:
            raise RuntimeError(f"Unexpected container ID format: {full_container_id}")
        container_id = match.group(1)

        # Use microk8s ctr to inspect container and get PID
        result = subprocess.run(
            ["sudo", "microk8s", "ctr", "containers", "info", container_id],
            capture_output=True, text=True, check=True
        )
        info = json.loads(result.stdout)

        # Extract PID from the container info
        # Warning: this is very specific to the containerd format and may vary according to your setup
        namespaces = info.get("Spec", {}).get("linux", {}).get("namespaces", [])
        for ns in namespaces:
            path = ns.get("path", "")
            match = re.search(r"/proc/(\d+)/ns/", path)
            if match:
                pid = match.group(1)
                print(f"PID do pod {pod_name} é {pid}")
                return pid
        raise RuntimeError(f"PID not found in container info for {pod_name}")


    # Brief: Connect the node to the internet via a veth pair
    # Params:
    #   string ip: IP address to assign to the node's interface
    #   int mask: Subnet mask (CIDR notation)
    #   string node_iface: Interface name inside the pod
    #   string host_iface: Interface name on the host
    # Returns:
    #   None
    def connectToInternet(self, ip: str, mask: int, node_iface: str, host_iface: str, reconnect: bool = False):
        if not reconnect:
            self._append_operation({
                "op": "connectToInternet",
                "ip": ip,
                "mask": mask,
                "node_iface": node_iface,
                "host_iface": host_iface
            })
        pid = self._getPodpid()
        self._create(node_iface, host_iface)
        self._setInterface(pid, node_iface)

        if self.__class__.__name__ == 'K8sSwitch' and hasattr(self, '_createPort'):
            self._createPort(self.nodeName, node_iface)

    
        subprocess.run(f"ip link set {host_iface} up", shell=True, check=True)
        subprocess.run(f"ip addr add {ip}/{mask} dev {host_iface}", shell=True, check=True)

        hostGateway = subprocess.run(
            "ip route show default | awk '{print $5}'",
            shell=True, capture_output=True
        ).stdout.decode().strip()

        print(f"[INFO] Host gateway: {hostGateway}")

        subprocess.run(f"iptables -t nat -I POSTROUTING -o {hostGateway} -j MASQUERADE", shell=True, check=True)
        subprocess.run(f"iptables -A FORWARD -i {host_iface} -o {hostGateway} -j ACCEPT", shell=True, check=True)
        subprocess.run(f"iptables -A FORWARD -i {hostGateway} -o {host_iface} -j ACCEPT", shell=True, check=True)

        print(f"[INFO] {self.nodeName} conectado à Internet com {ip}/{mask}")


    # Brief: Create a veth pair
    # Params:
    #   string peer1Name: Name of the first interface
    #   string peer2Name: Name of the second interface
    # Returns:
    #   None
    def _create(self, peer1Name: str, peer2Name: str) -> None:
        # Remove if exists 
        subprocess.run(f"ip link del {peer1Name}", shell=True, check=False, stderr=subprocess.DEVNULL) 
        subprocess.run(f"ip link del {peer2Name}", shell=True, check=False, stderr=subprocess.DEVNULL)
        try:
            subprocess.run(f"ip link add {peer1Name} type veth peer name {peer2Name}", shell=True, check=True)
            print(f"[INFO] Par veth {peer1Name}<->{peer2Name} criado")
        except Exception as ex:
            raise Exception(f"Error while creating veth pair {peer1Name}<->{peer2Name}: {str(ex)}")


    # Brief: Move one end of the veth pair into the pod's network namespace and bring it up
    # Params:
    #   int pid: PID of the pod's main container
    #   string peerName: Name of the interface to move into the pod
    # Returns:
    #   None
    def _setInterface(self, pid: int, peerName: str) -> None:
        try:
            subprocess.run(f"ip link set {peerName} netns {pid}", shell=True, check=True)
            subprocess.run(f"nsenter -t {pid} -n ip link set {peerName} up", shell=True, check=True)
            print(f"[INFO] Interface {peerName} movida para pod {self.nodeName} (PID {pid}) e ativada")
        except Exception as ex:
            raise Exception(f"Error while setting interface {peerName} in pod {self.nodeName} (PID {pid}): {str(ex)}")


    # Brief: Set the default gateway inside the pod
    # Params:
    #   string gateway_ip: IP address of the gateway
    #   string interfaceName: Interface name to use as the default route
    # Returns:
    #   None
    def setDefaultGateway(self, gateway_ip: str, interfaceName: str, reconnect: bool = False):
        if not reconnect:
            self._append_operation({
                "op": "setDefaultGateway",
                "gateway_ip": gateway_ip,
                "iface_peer": interfaceName
            })

        pid = self._getPodpid()
        try:
            # delete k8s deafult gateway if exists
            subprocess.run(f"nsenter -t {pid} -n ip route del default", shell=True, check=False)
            subprocess.run(f"nsenter -t {pid} -n ip route add default via {gateway_ip} dev {interfaceName}", shell=True, check=True)
            print(f"[INFO] Default gateway {gateway_ip} set on {interfaceName} in pod {self.nodeName}")
        except Exception as ex:
            raise Exception(f"Error setting default gateway {gateway_ip} on {interfaceName} in {self.nodeName}: {str(ex)}")


    # Brief: Add a static route inside the pod
    # Params: 
    #   string ip: Destination IP address
    #   string mask: Subnet mask (CIDR notation)
    #   string interfaceName: Interface name to use for the route
    # Returns:
    #   None
    def addRoute(self, ip: str, mask: str, interfaceName: str):
        pid = self._getPodpid()
        try:
            subprocess.run(f"nsenter -t {pid} -n ip route add {ip}/{mask} dev {interfaceName}", shell=True, check=True)
            print(f"[INFO] Route {ip}/{mask} via {interfaceName} added in pod {self.nodeName}")
        except Exception as ex:
            raise Exception(f"Error adding route {ip}/{mask} via {interfaceName} in {self.nodeName}: {str(ex)}")


    # Brief: Wait until the pod is in Running state and ready
    # Params:
    #   int timeout: Maximum time to wait in seconds (default: 600)
    # Returns:
    #   None
    def _waitUntilReady(self, timeout: int = 600):
        for _ in range(timeout):
            try:
                pod = self.api.read_namespaced_pod(name=self.nodeName, namespace="default")
                if pod.status.phase == "Running":
                    # Check if all containers are ready
                    conditions = pod.status.conditions or []
                    ready = any(c.type == "Ready" and c.status == "True" for c in conditions)
                    if ready:
                        return
            except client.exceptions.ApiException as e:
                if e.status != 404:
                    raise
            time.sleep(1)
        raise TimeoutError(f"Pod {self.nodeName} did not become ready within {timeout} seconds.")


    # Brief: Generate kubeconfig file for accessing the cluster
    # Params:
    # path: Path to save the kubeconfig file
    # Returns:
    #   None
    def _generateKubeconfig(self, path: str):
        try:
            result = subprocess.run(
                ["sudo", "microk8s", "config"],
                capture_output=True, text=True, check=True
            )
            kubeconfig = result.stdout
            with open(path, "w") as f:
                    f.write(kubeconfig)

        except subprocess.CalledProcessError as e:
            print("Failed to generate kubeconfig:", e.stderr)
            raise
        except Exception as e:
            print("Error creating kubeconfig:", str(e))
            raise


    # Brief: Build the StatefulSet manifest for Kubernetes, to ensure stable network identity
    # Params:
    #   None
    # Returns:
    #   StatefulSet manifest (dict)
    def _buildStatefulSetManifest(self):
        security_context = {"capabilities": {"add": ["NET_ADMIN", "NET_RAW"]}}
        if self.privileged:
            security_context["privileged"] = True

        return {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {
                "name": f"{(self.nodeName)[:-2]}",
                "labels": {"app": self.app}
            },
            "spec": {
                "serviceName": f"{(self.nodeName)[:-2]}",  # precisa do headless service
                "replicas": 1,
                "selector": {"matchLabels": {"app": self.app}},
                "template": {
                    "metadata": {"labels": {"app": self.app}},
                    "spec": {
                        "containers": [{
                            "name": "main",
                            "image": self.image,
                            "stdin": True,
                            "tty": True,
                            "securityContext": security_context,
                            "resources": {
                                "limits": {
                                    "cpu": self.cpu,
                                    "memory": self.memory
                                }
                            }
                        }],
                        "restartPolicy": "Always"
                    }
                }
            }
        }



    # Brief: Append an operation to the pod's StatefulSet annotations for persistence
    # Params:
    #  dict operation: Operation to append
    # Returns:
    #  None
    def _append_operation(self, operation):
        ss = self.apps_api.read_namespaced_stateful_set(self.nodeName[:-2], "default")
        annotations = ss.metadata.annotations or {}

        ops = json.loads(annotations.get("lft/operations", "[]"))

        ops.append(operation)
        annotations["lft/operations"] = json.dumps(ops)

        patch = {"metadata": {"annotations": annotations}}
        self.apps_api.patch_namespaced_stateful_set(
            name=ss.metadata.name,
            namespace="default",
            body=patch
        )




