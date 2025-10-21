from k8s_lft.node import K8sNode
import subprocess



# Brief: Kubernetes Open vSwitch switch node.
# Inherits from K8sNode to leverage pod management and networking capabilities.
# This class encapsulates the functionality to create and manage an Open vSwitch
# instance within a Kubernetes pod, allowing it to act as a virtual switch in a
# software-defined network (SDN) environment.
class K8sSwitch(K8sNode):

    def __init__(self, name):
        super().__init__(name, image="gns3/openvswitch")


    # Brief: Instantiate the switch pod and set up Open vSwitch bridge.
    # Params:
    #   kwargs: Additional keyword arguments for pod instantiation.
    # Returns:
    #   None
    def instantiate(self, **kwargs):
        super().instantiate(**kwargs)
        self._createBridge()

    # Brief: Create an Open vSwitch bridge inside the switch pod.
    # Params:
    #   None
    # Returns:
    #   None
    def _createBridge(self):
        # check if bridge already exists
        try:
            subprocess.run(f"sudo microk8s kubectl exec {self.nodeName} -- ovs-vsctl br-exists {self.nodeName[:-2]}", check=True, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            subprocess.run(f"sudo microk8s kubectl exec {self.nodeName} -- ovs-vsctl add-br {self.nodeName[:-2]}", check=True, shell=True)
            subprocess.run(f"sudo microk8s kubectl exec {self.nodeName} -- ip link set {self.nodeName[:-2]} up", check=True, shell=True)


    # Brief: Connect an interface to the Open vSwitch bridge.
    # Params:
    #   string iface: Name of the interface to connect.
    #   string controller_ip: IP address of the SDN controller.
    #   string controller_port: Port of the SDN controller (default: 6653).
    #   string protocol: Protocol to use for controller connection (default: "tcp").
    # Returns:
    #   None
    def setController(self, controller_ip: str, controller_port: int = 6653, protocol: str = "tcp", reconnect: bool = False):
        if not reconnect:
            self._append_operation({
                "op": "setController",
                "controller_ip": controller_ip,
                "controller_port": controller_port,
                "protocol": protocol
            })
        # Remove controladores antigos, se houver
        self.run(f"ovs-vsctl del-controller {self.nodeName[:-2]} || true")
        # Adiciona o controlador remoto
        self.run(f"ovs-vsctl set-controller {self.nodeName[:-2]} {protocol}:{controller_ip}:{controller_port}")
        # Confirma o modo do switch (geralmente "secure" evita conectar a outros controladores)
        self.run(f"ovs-vsctl set-fail-mode {self.nodeName[:-2]} secure")


    # Brief: Connect an interface to the Open vSwitch bridge.
    # Params:
    #   string iface: Name of the interface to connect.
    # Returns:
    #   None
    def _connectInterface(self, iface: str):
        self.run(f"ovs-vsctl add-port {self.nodeName[:-2]} {iface}")
        self.run(f"ip link set {iface} up")


    # Brief: Create and connect a veth pair between this switch and another node.
    # Params:
    #  string nodeName: Name of the other node to connect to.
    #  string peerInterfaceName: Name of the interface on the other node.
    # Returns:
    #  None
    def _createPort(self, nodeName, peerInterfaceName) -> None:
        try:
            self.run(f"ovs-vsctl add-port {nodeName[:-2]} {peerInterfaceName}")
            print(f"[INFO] Porta {peerInterfaceName} adicionada ao switch {nodeName[:-2]}")
        except Exception as ex:
            raise Exception(f"Error while creating port {peerInterfaceName} in switch {nodeName[:-2]}: {str(ex)}")
