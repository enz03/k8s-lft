from kubernetes import client, config, watch
import threading
import time
import json
import traceback
from requests.exceptions import ConnectionError as RequestsConnectionError
from urllib3.exceptions import NewConnectionError, MaxRetryError





# Singleton K8sWatcher to monitor pod status and trigger reapplication of operations
class K8sWatcher:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        else:
            print("[Watcher] Já existe um watcher, retornando instância existente.")
        return cls._instance

    def __init__(self, namespace="default", label_selector=None):
        if hasattr(self, "_initialized") and self._initialized:
            return


        # internal state
        self.nodes = dict()
        self.node_objects = dict()
        self._initialized = True
        self.namespace = namespace
        self.label_selector = label_selector
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.__watch_loop)
        self.thread.start()



    # Brief: Register a node object for operation reapplication.
    # Params:
    #   node: The node object to register.
    # Returns:
    #   None
    def registerNode(self, node):
        self.node_objects[node.nodeName] = node


    # Brief: Main watch loop to monitor pod status and trigger reapplication of operations.
    # Params:
    #   None
    # Returns:
    #   None
    def __watch_loop(self):

        # Brief: Wait for a pod to be in Running state and then reapply operations.
        # Params:
        #   string pod_name: Name of the pod to monitor.
        # Returns:
        #   None
        def __waitForRunningThenApply(pod_name):
            print(f"[Watcher] Aguardando pod {pod_name} entrar em Running para reaplicar operações...")
            for i in range(60):  # try for up to 60 seconds
                try:
                    print(f"[Watcher] ({i}) Consultando status do pod {pod_name}...")
                    pod_status = v1.read_namespaced_pod_status(pod_name, self.namespace)
                    phase = pod_status.status.phase
                    print(f"[Watcher] Pod {pod_name} está com phase={phase}")
                    if phase == "Running":
                        print(f"[Watcher] Pod {pod_name} agora está em Running, reaplicando operações...")
                        self.reapplyOperations(pod_name)
                        print(f"[Watcher] Operações reaplicadas para {pod_name}, "
                            f"reapply está como {self.nodes[pod_name]['redo_operations']}.")
                        break
                except Exception as e:
                    print(f"[Watcher] Erro ao ler status do pod {pod_name}: {e}")
                time.sleep(1)
            else:
                print(f"[Watcher] Timeout: pod {pod_name} não entrou em Running em 30s.")

        config.load_kube_config(config_file="kubeconfig")
        v1 = client.CoreV1Api()
        w = watch.Watch()

        print(f"[Watcher] Iniciando observação de pods no namespace '{self.namespace}'")
        while not self.stop_event.is_set():
            try:
                
                for event in w.stream(
                    v1.list_namespaced_pod,
                    namespace=self.namespace,
                    label_selector=self.label_selector,
                    timeout_seconds=60
                ):
                    if self.stop_event.is_set():
                        break

                    pod = event["object"]
                    pod_name = pod.metadata.name
                    uid = pod.metadata.uid
                    phase = pod.status.phase
                    
                    if pod_name not in self.nodes:
                        
                        self.nodes[pod_name] = {
                            "uid": uid,
                            "last_phase": phase,
                            "recreate_count": 0,
                            "running_transitions": 0,
                            "redo_operations": False
                        }
                        
                    if uid != self.nodes[pod_name]["uid"] or self.nodes[pod_name]["redo_operations"]:
                        if uid != self.nodes[pod_name]["uid"]:
                            self.nodes[pod_name]["uid"] = uid
                            self.nodes[pod_name]["recreate_count"] += 1
                            self.nodes[pod_name]["redo_operations"] = True

                            # redo whole network if a pod was recreated
                            for node in self.nodes.values():
                                print(f"[Watcher] Marcando nó {node} para reapply devido a erro no watch.")
                                node["redo_operations"] = True
                            print(f"[Watcher] Pod {pod_name} foi recriado (recreate_count={self.nodes[pod_name]['recreate_count']}).")

                        # do switches first, they have to be up for others to connect
                        switches_to_reapply = [n for n in self.nodes if n.startswith("s") and self.nodes[n]["redo_operations"]]
                        if switches_to_reapply:
                            print(f"[Watcher] Detectados switches a reaplicar: {switches_to_reapply}")


                            for s_name in switches_to_reapply:
                                print(f"aplicando __waitforRunning em {s_name}")
                                __waitForRunningThenApply(s_name)
                                print(f"aplicou __waitforRunning em {s_name}?")
                                self.nodes[s_name]["redo_operations"] = False  

                            for n in self.nodes:
                                if not n.startswith("s"):  
                                    self.nodes[n]["redo_operations"] = True
                                    print(f"[Watcher] Marcando {n} para reapply (switch foi recriado).")

                        # then connect the rest
                        others_to_reapply = [n for n in self.nodes if not n.startswith("s") and self.nodes[n]["redo_operations"]]
                        if others_to_reapply:
                            print(f"[Watcher] Reaplicando operações para os demais pods: {others_to_reapply}")
                            for n_name in others_to_reapply:
                                __waitForRunningThenApply(n_name)
                                self.nodes[n_name]["redo_operations"] = False

                        continue


            except Exception as e:
                print(f"[Watcher] Erro no stream: {e}. Reiniciando em 2s...")
                err_msg = str(e)

                is_connection_error = (
                    isinstance(e, RequestsConnectionError)
                    or isinstance(e, NewConnectionError)
                    or isinstance(e, MaxRetryError)
                    or "Connection refused" in err_msg
                    or "Max retries exceeded" in err_msg
                    or "Failed to establish a new connection" in err_msg
                )

                if is_connection_error:
                    for node in self.nodes.values():
                        print(f"[Watcher] Marcando nó {node} para reapply devido a erro no watch.")
                        node["redo_operations"] = True

                time.sleep(2)

            finally:
                print("[Watcher] um evento aconteceu...")





    # Brief: Reapply stored operations to a pod.
    # Params:
    #   string pod_name: Name of the pod to reapply operations to.
    # Returns:
    #   None
    def reapplyOperations(self, pod_name):
        print(f"[Watcher] Reaplicando operações para {pod_name}...")

        node_object = self.node_objects.get(pod_name)

        apps_v1 = client.AppsV1Api()
        statefulset_name = pod_name[:-2]  # remove "-0"
        try:
            statefulset = apps_v1.read_namespaced_stateful_set(
                name=statefulset_name,
                namespace=self.namespace
            )

            annotations = statefulset.metadata.annotations or {}
            ops_json = annotations.get("lft/operations", "[]")
            ops = json.loads(ops_json)

            print(f"[Watcher] StatefulSet '{statefulset_name}' encontrado com {len(ops)} operação(ões).")
            for op in ops:
                print(f"[Watcher] Reaplicando operação: {op}")
                self.executeOperation(self.node_objects[pod_name], pod_name, op)
            self.nodes[pod_name]["redo_operations"] = False

        except client.exceptions.ApiException as e:
            print(f"[Watcher] Erro ao buscar StatefulSet '{statefulset_name}': {e}")




    # Brief: Execute a specific operation on a node.
    # Params:
    #   node: The node object to operate on.
    #   string pod_name: Name of the pod.
    #   dict operation: The operation to execute.
    # Returns:
    #   None
    def executeOperation(self, node, pod_name, operation):
        print(f"[Watcher] Executando operação '{operation}' no pod '{pod_name}'") 

        if node.__class__.__name__ == 'K8sSwitch':
            node._createBridge()
            print(f"[Watcher] Bridge criada no switch {pod_name}")


        match operation["op"]:
            case "connect":
                node.connect(operation["peer"], operation["interface_name"], operation["peer_interface_name"], reconnect=True)
            case "setIp":
                node.setIp(operation["ip"], operation["mask"], operation["interface"], reconnect=True)
            case "setDefaultGateway":
                node.setDefaultGateway(operation["gateway_ip"], operation["iface_peer"], reconnect=True)
            case "setController":
                node.setController(operation["controller_ip"], operation["controller_port"], operation["protocol"], reconnect=True)
            case "initController":
                node.initController(operation["ip"], operation["port"], operation["app_path"], reconnect=True)
            case "connectToInternet":
                node.connectToInternet(operation["ip"], operation["mask"], operation["node_iface"], operation["host_iface"], reconnect=True)
            case _:
                print(f"[Watcher] Operação desconhecida: {operation['op']}")
        pass




