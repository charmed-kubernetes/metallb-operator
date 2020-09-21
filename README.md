# MetalLB Operator

## Overview

The MetalLB Operator offers a software network load balancing implementation that allows
for LoadBalancing services in Kubernetes.

This Operator deploys a charm bundle to a Juju K8s model. The bundle is composed of the 
charm metallb-controller and the charm metallb-speaker. These individual charms can be 
found under the `charms/` directory.

Upstream documentation can be found here : <https://metallb.universe.tf/>

MetalLB has two modes of operation: Layer 2 or BGP. Both concepts are explained here
https://ubuntu.com/kubernetes/docs/metallb. This charm currently supports *only* the
layer 2 mode.

## Deploying

### Setup

Setting up this bundle requires a Kubernetes cluster, either on public cloud,
on-premises cloud, or even on a MicroK8s single-node deployment. 

### Setup MicroK8s

You will need to install these snaps to get started:

    sudo snap install juju --classic
    sudo snap install microk8s --classic

Next, you will need to add yourself to the `microk8s` group:

    sudo usermod -aG microk8s $USER
    newgrp microk8s

Once MicroK8s is installed, you can verify that it is running adequately with:

    microk8s.status

For Juju to bootstrap a microk8s controller, two addons need to be enabled:

    microk8s.enable dns storage

Once that is done, you can bootstrap a juju controller:

    juju bootstrap microk8s

### Deploy the bundle

The charm is by default using a layer 2 configuration, and the ip range 
"192.168.1.240-192.168.1.250". You can use a bundle.yaml config to edit these,
or use the juju config command line to edit it post-deployment. 

    juju add-model metallb-system
    juju deploy cs:~charmed-kubernetes/metallb-bundle

#### Post-deployment config

    juju config metallb-controller iprange=<IPRANGE>

#### Bundle configuration

A bundle.yaml would look like this:
```
description: A charm bundle to deploy MetalLB in Kubernetes
bundle: kubernetes
applications:
  metallb-controller:
    charm: cs:~charmed-kubernetes/metallb-controller
    scale: 1
    options:
      iprange: "192.168.1.88-192.168.1.89" #Change this!
  metallb-speaker:
    charm: cs:~charmed-kubernetes/metallb-speaker
    scale: 1
```
You would then deploy the bundle by calling this local file:
    juju deploy ./bundle.yaml

## Note: Using RBAC

If RBAC is enabled in the Kubernetes cluster, an extra deployment
step is required. Before deploying metallb, apply the manifest 
docs/rbac-permissions-controller.yaml. This manifest gives permissions
to the controller pods to use the K8s API to create the necessary resources
to make MetalLB work.

    wget https://raw.githubusercontent.com/charmed-kubernetes/metallb-operator/master/docs/rbac-permissions-controller.yaml
    microk8s.kubectl apply -f rbac-permissions-controller.yaml

This manifest refers to the namespace where MetalLB will be deployed as 
`metallb-system`. If you give another name to your namespace, edit the manifest
before applying it.

If you forgot to apply this manifest before deploying MetalLB, the units will
fail in the start hook. But don't worry! You can apply the manifest afterwards,
and the resolve the units that are in error to solve the problem.

    juju resolve metallb-controller/0
    juju resolve metallb-speaker/0

## Using MetalLB

Once deployed, metallb will automatically assign ips from the range given to it
to services of type `Load Balancer`. When the services are deleted, the ips are
available again. MetalLB will only use the ips allocated in the pool(s) given to
it, and more than one pool can be assigned as well. 

## Example

To test the usage of metallb, a simple webapp can be deployed. 
An example manifest is included in this bundle, under `docs/example-microbot-lb.yaml`.
You can use it by copying it locally:

    wget https://raw.githubusercontent.com/charmed-kubernetes/metallb-operator/master/docs/example-microbot-lb.yaml
    microk8s.kubectl apply -f example-microbot-lb.yaml
    microk8s.kubectl get service microbot-lb

The EXTERNAL-IP is the ip assigned to the microbot service by the MetalLB controller. 
If you reach this IP with a browser, you should see the image of a microbot. If you
cannot, most probably the ip range is not correctly chosen. The ip range needs to
be a reserved pool uniquely for metallb, to avoid ip conflicts. 

To remove the example, simply delete the manifest with kubectl:

    microk8s.kubectl delete -f example-microbot-lb.yaml

## Removing MetalLB

To remove metallb from the cluster, you can remove each application separately:

    juju remove-application metallb-controller
    juju remove-application metallb-speaker

or alternatively, you can delete the model itself (be careful, if you deployed 
additional things in this model, then these things would be deleted as well):

    juju remove-model metallb-system

## Developing

To edit this charm and run it locally to test changes, pull this repo:

    git clone https://github.com/charmed-kubernetes/metallb-operator.git

If you plan on proposing edits to the operator, please fork the repo
before pulling it.

To build the charm, simply use tox in the base folder:

    cd metallb-bundle
    tox -e build

Edit the bundle.yaml to point to local charms instead of the charmhub.

    metallb-controller:
        charm: ./charms/metallb-controller/.build/metallb-controller.charm
    metallb-speaker:
        charm: ./charms/metallb-speaker/.build/metallb-speaker.charm

Make sure you have juju bootstrapped to some k8s cluster, and go for it:

    juju add-model metallb-system
    juju deploy .
