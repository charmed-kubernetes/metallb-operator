# MetalLB Operator

## Overview

MetalLB offers a software network load balancing implementation that allows for
LoadBalancing services in Kubernetes. Upstream documentation for MetalLB can be
found at <https://metallb.universe.tf/>

The charm currently supports MetalLB Layer 2 mode. 

The official documentation for this charm and how to use it with Kubernetes
can be found at <https://ubuntu.com/kubernetes/docs/metallb>.

## Configuration

The `namespace` config option allows users to specify a namespace that the MetalLB resources will be deployed into when
first installed. This namespace will be created by the charm and should not exist before deployment. 
It defaults to `metallb-system`, as this is the upstream default. 

The `image-registry` config option sets the image registry used for any MetalLB pods. It defaults to 
`rocks.canonical.com:443/cdk`. Note that this charm is workload-less, so there are no OCI-image resources associated with
it, as the charm simply applies a manifest via the Kubernetes API. You will need to use a registry that contains 
the speaker and controller images required by the upstream manifest. 

The `metallb-release` config option controls what version of the manifest to deploy. Currently, this charm only supports
deploying 1 manifest version, v0.13.10, but more are expected to be added in the future as the Metallb project 
progresses

The `iprange` config option specifies IP ranges and CIDRs that load-balancer services will consume. 
This should be a comma-separated list of hyphenated IP address ranges or CIDRs. 

## Switching from the old pod-spec metallb-controller and metallb-speaker charms to the new charm

With the old pod-spec charms, you would typically create a model named metallb-system and deploy the charms into that. 
To begin using the new charm, you can create a new model (called whatever you prefer, just not metallb-system) and deploy the new charm. You will 
need to supply a `namespace` config option with something other than `metallb-system` (as that namespace already contains
a MetalLB installation) so that the new Metallb resources can be created in that. Once the charm comes up, the new 
MetalLB installation will take over managing existing LoadBalancer services, and the model containing the old charms 
can be deleted. 

## Filing bugs

Please file bugs at https://bugs.launchpad.net/operator-metallb.

## Building the charm

The charms can be built locally using [charmcraft][]:

```bash
charmcraft pack 
```

## Testing locally

The easiest way to test MetalLB locally is with [MicroK8s][]. Note that
MicroK8s and Juju are not strictly build dependencies, so you may need
to install them yourself:

```bash
snap install juju --classic
snap install microk8s --classic
sudo usermod -aG microk8s $USER
newgrp microk8s
microk8s.enable dns storage
```

Once that is done, you can bootstrap a Juju controller into MicroK8s and deploy a locally-packed charm

```bash
juju bootstrap microk8s
juju add-model metallb
charmcraft pack
juju deploy <charm-file-name>
```

<!-- Links -->
[charmcraft]: https://github.com/canonical/charmcraft/
[MicroK8s]: http://microk8s.io/

