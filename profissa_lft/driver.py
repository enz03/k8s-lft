from profissa_lft.host import Host as DockerHost
from profissa_lft.switch import Switch as DockerSwitch
from profissa_lft.controller import Controller as DockerController

from k8s_lft.host import K8sHost
from k8s_lft.switch import K8sSwitch
from k8s_lft.controller import K8sController

BACKEND = "k8s"  # or "docker", for docker-based implementation
if BACKEND == "k8s":
    Host = K8sHost
    Switch = K8sSwitch
    Controller = K8sController
else:
    Host = DockerHost
    Switch = DockerSwitch
    Controller = DockerController
