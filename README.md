# MetalLB Operator

## Overview

MetalLB offers a software network load balancing implementation that allows for
LoadBalancing services in Kubernetes. Upstream documentation for MetalLB can be
found at <https://metallb.universe.tf/>

The official documentation for these charms and how to use them with Kubernetes
can be found at <https://ubuntu.com/kubernetes/docs/metallb>.

This repo contains both of the MetalLB charms (under the [charms][] directory),
as well as the bundle (under the [bundle][] directory).

## Building the charms

The charms can be built locally using the `Makefile`:

```bash
make charms
```

This will first check for any missing dependencies, such as [charmcraft][], and
install them if necessary (so you may receive a `sudo` prompt to perform the
package installation). Then it will build the charms, creating a `build/`
directory with the two `.charm` files in it.

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

Once that is done, you can bootstrap a Juju controller into MicroK8s, add a
Kubernetes model, and deploy the bundle using the [local overlay][]:

```bash
juju bootstrap microk8s
juju add-model metallb-system
juju deploy ./bundle --overlay ./docs/local-overlay.yaml
```

There is also an [included manifest][microbot-manifest] for deploying microbot
to test your deployment:

```bash
microk8s.kubectl apply -f ./docs/example-microbot-lb.yaml
```

<!-- Links -->
[charms]: charms
[bundle]: bundle
[charmcraft]: https://github.com/canonical/charmcraft/
[MicroK8s]: http://microk8s.io/
[local overlay]: docs/local-overlay.yaml
[microbot-manifest]: docs/example-microbot-lb.yaml
