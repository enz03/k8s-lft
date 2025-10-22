# Lightweight Fog Testbed (LFT)

## Overview

The Lightweight Fog Testbed (LFT) is a framework designed to easily create lightweight network topologies. By leveraging Docker containers, LFT allows you to add any container to the network to provide network services or emulate network devices, such as switches and controllers, particularly in Software Defined Networking (SDN) scenarios. The framework integrates with OpenvSwitch to emulate network forwarding devices and uses srsRAN 4G to simulate wireless links for Fog and Edge applications.

## 1. Requirements

LFT was developed and tested on **Ubuntu Desktop 24.04 LTS**. It is recommended to use this version of Ubuntu for optimal compatibility.

## 2. Installation

To install the LFT framework, follow these steps:

1. **Clone the repository**:

   ```bash
   git clone https://github.com/enz03/k8s-lft.git
   cd k8s-lft
   ```

### 2.1 Create a Virtual Environment

It’s recommended to set up a virtual environment to isolate dependencies.

### 2.2 Install Required Modules

Once your virtual environment is set up, install the required modules:

```bash
pip install -e .
```

If any dependencies are missing, you can manually clone the repository and run the dependencies installation script.

### 2.3 Install Additional Dependencies

To install the necessary dependencies, use the following commands:

```bash
chmod +X dependencies.sh
./dependencies.sh
```

## 3. First Run

### Choosing a Driver

You can choose the backend driver based on your desired setup. The options are Kubernetes or Docker.

#### Using Kubernetes as the Driver

1. **Disable Firewalld**:
   Before running with Kubernetes, you’ll need to disable the firewall to allow Kubernetes services to function correctly.

   ```bash
   sudo systemctl stop firewalld
   ```

2. **Run the Example SDN Topology**:
   At the root of the project, run the following command to start the topology:

   ```bash
   sudo ./<YOUR_ENV_NAME>/bin/python3 ./examples/simpleSDNTopology.py
   ```

3. **Visualize the Results**:
   To visualize the results in Grafana, port-forward the Prometheus service from the `observability` namespace:

   ```bash
   sudo microk8s kubectl port-forward -n observability svc/kube-prom-stack-grafana 3000:80
   ```

   Then, open your browser and go to [http://localhost:3000](http://localhost:3000) to access Grafana.

 4. **Resetting the Environment**:
    After experimenting, you can reset your environment to its initial state by running:
    
    ```bash
    sudo ./k8s_lft/utils/reset_k8s.sh
    ```

#### Using Docker as the Driver

1. **Change the Driver Configuration**:
   If you want to use Docker instead of Kubernetes, update the driver setting in the `driver.py` file. Modify the line in `/profissa_lft/driver.py` as follows:

   ```python
   BACKEND = "docker"  # <-- change from "k8s" to "docker"
   ```

2. **Run the Example SDN Topology**:
   After changing the backend, run the topology again with the same command:

   ```bash
   sudo ./<YOUR_ENV_NAME>/bin/python3 ./examples/simpleSDNTopology.py
   ```

---

## 4. Troubleshooting with the Docker Driver

If you encounter any issues while running LFT scripts, try the following troubleshooting steps:

1. **Check Dependencies**: Make sure all required dependencies are installed. If not, refer to the installation section above to install them.

2. **Verify Ubuntu Version**: Ensure you're using Ubuntu Desktop **24.04 LTS** as this is the version LFT has been developed and tested on.

3. **Check Docker Containers**:
   If containers are not running as expected, check if they are instantiated using:

   ```bash
   docker ps -a
   ```

   If containers are found, you can either remove them with:

   ```bash
   docker system prune
   ```

   Or forcefully stop them with:

   ```bash
   docker rm -f <container_name>
   ```

4. **Check Docker Images**:
   Ensure the Docker image required by LFT is available locally:

   ```bash
   docker images
   ```

   If the image is not found, verify that it exists on [Docker Hub](https://hub.docker.com/), or check the Docker folder in the project for instructions on building the image.

5. **Build Issues**: If the image fails to build, check the `docker` folder for any specific instructions or troubleshooting tips related to building the images.

---

## 5. Troubleshooting with the Kubernetes Driver

If you are using the Kubernetes backend and experience issues, follow the steps below:

1. **Check Cluster Status**:
   Ensure that MicroK8s is running correctly:

   ```bash
   sudo microk8s status --wait-ready
   ```

2. **Check Pod States**:
   List all running pods in the default or observability namespace:

   ```bash
   sudo microk8s kubectl get pods -A
   ```

   To investigate a specific pod:

   ```bash
   sudo microk8s kubectl describe pod <pod_name> -n <namespace>
   sudo microk8s kubectl logs <pod_name> -n <namespace>
   ```

3. **Reset and Re-deploy**:
   If problems persist, you can reset the entire Kubernetes environment:

   ```bash
   sudo ./k8s_lft/utils/reset_k8s.sh
   ```
   

4. **Verify Certificates**:
   Ensure the Kubernetes CA certificate (`ca.crt`) has been correctly issued. You can check it with:

   ```bash
   sudo ls /var/snap/microk8s/current/certs/ca.crt
   ```

   If the file is missing or invalid, reinitialize MicroK8s:

   ```bash
   sudo microk8s stop
   sudo microk8s start
   ```

5. **Check Observability Addons**:
   If Grafana or Prometheus dashboards are empty, confirm that the observability services are active:

   ```bash
   sudo microk8s kubectl get pods -n observability
   ```

   Reinstall if needed:

   ```bash
   sudo microk8s disable observability
   sudo microk8s enable observability
   ```
