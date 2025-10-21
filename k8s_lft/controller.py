from .node import K8sNode
import time

# Brief: Kubernetes SDN controller node.
# Inherits from K8sNode to leverage pod management and networking capabilities.
# This class encapsulates the functionality to create and manage an SDN controller
class K8sController(K8sNode):

    def __init__(self, nodeName):
        super().__init__(nodeName, image="osrg/ryu")


    # Brief: Instantiate the controller pod.
    # Params:
    #   kwargs: Additional keyword arguments for pod instantiation.
    # Returns:
    #   None
    def instantiate(self, **kwargs):
        super().instantiate(**kwargs)
        # Pode iniciar o Ryu depois que o pod estiver pronto
        #print(f"[INFO] Controller {self.nodeName} pronto para iniciar Ryu")


    # Brief: Initialize the Ryu SDN controller inside the pod.
    # Params:
    #   string ip: IP address to bind the controller to (default: pod's IP).
    #   int port: Port to listen on (default: 6653).
    #   string app_path: Path to the Ryu application to run (default: "ryu.app.simple_switch_13").
    #   bool reconnect: Whether this is a reconnection attempt (default: False).
    # Returns:
    #   None
    def initController(self, ip=None, port=6653, app_path="ryu.app.simple_switch_13", reconnect: bool = False):
        if not reconnect:
            self._append_operation({
                "op": "initController",
                "ip": ip or self.getIp(),
                "port": port,
                "app_path": app_path
            })
        ip = ip or self.getIp()
        #print(f"[INFO] Iniciando Ryu no {ip}:{port} com app {app_path}")
        self.run(f"nohup ryu-manager --ofp-tcp-listen-port {port} {app_path} > /tmp/ryu.log 2>&1 &")
        self.__waitForRyu(port)


    # Brief: Wait for the Ryu controller to start listening on the specified port.
    # Params:
    #   int port: Port to check (default: 6653).
    #   int timeout: Maximum wait time in seconds (default: 600).
    # Returns:
    #   None
    def __waitForRyu(self, port=6653, timeout=600):
        for _ in range(timeout):
            try:
                out = self.run("ss -lntp")
                if str(port) in out:
                    return True
            except Exception:
                pass
            time.sleep(1)
        raise TimeoutError(f"Ryu controller não respondeu na porta {port}.")


    # Brief: Get the IP address of the controller pod.
    # Params:
    #   None
    # Returns:
    #   string: IP address of the pod.
    def getIp(self):
        return self.run("hostname -i").strip().split()[0]
