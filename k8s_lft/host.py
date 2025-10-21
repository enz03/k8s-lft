from .node import K8sNode

class K8sHost(K8sNode):
    """
    K8sHost extends K8sNode to represent a host in Kubernetes.
    It can be used to create and manage pods that act as hosts in a network simulation.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)