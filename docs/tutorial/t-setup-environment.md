# Environment Setup
This is part of the [Charmed MetalLB Tutorial](/t/charmed-metalb-tutorial-overview/11359?channel=1.28/stable). Please refer to this page for more information and the overview of the content.

## Minimum requirements
Before we start, make sure your Kubernetes cloud meeting the following requirements:
- Access to the internet for downloading the required charms and containers
- Access to a Kubernetes Cloud either 
  * [deployed via microk8s](https://juju.is/docs/juju/get-started-with-juju#heading--prepare-your-cloud)
  * [deployed via charmed-kubernetes](https://ubuntu.com/kubernetes/docs/quickstart)
  * or otherwise deployed

## Represent the cloud in juju
Juju recognizes your MicroK8s cloud automatically. You can already see it if you run:
```shell
juju clouds
```

```
Cloud      Regions  Default    Type  Credentials  Source    Description
microk8s   1        localhost  k8s   1            built-in  A Kubernetes Cluster
```

If it is not there, you may add the cloud with:
```shell
KUBECONFIG=path/to/kubeconfig/file  juju add-k8s --client <k8s-cloud>
```
