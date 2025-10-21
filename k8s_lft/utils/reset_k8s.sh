#!/bin/bash
# Deleta todos os pods com a label app=k8s-node no namespace default
sudo microk8s kubectl delete pods -l app=k8s-node -n default

# Deleta todos os StatefulSets com a label app=k8s-node no namespace default
sudo microk8s kubectl delete statefulsets -l app=k8s-node -n default

# Deleta todos os Deployments com a label app=k8s-node no namespace default
sudo microk8s kubectl delete deployments -l app=k8s-node -n default

# Deleta todos os Services com a label app=k8s-node no namespace default
sudo microk8s kubectl delete services -l app=k8s-node -n default