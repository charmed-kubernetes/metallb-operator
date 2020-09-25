## Overview

MetalLB offers a software network load balancing implementation that allows for
LoadBalancing services in Kubernetes. Upstream documentation for MetalLB can be
found at <https://metallb.universe.tf/>

The official documentation for these charms and how to use them with Kubernetes
can be found at <https://ubuntu.com/kubernetes/docs/metallb>.

## Deploying

The following will deploy MetalLB with the default layer 2 configuration and IP
range "192.168.1.240-192.168.1.250":

```sh
juju deploy cs:~containers/metallb
```

You will likely want to change the IP range to suit your environment, either
via a [bundle overlay][] or a subsequent command:

The IP range allocated to MetalLB can be controlled via the configuration of the
metallb-controller:

```
juju config metallb-controller iprange="192.168.1.240-192.168.1.250"
```

Multiple IP pools can be specified as well, if using a CIDR notation delimited by
a comma:

```
juju config metallb-controller iprange="192.168.1.240/28, 10.0.0.0/28"
```

Please see the [documentation](https://ubuntu.com/kubernetes/docs/metallb) for
more details.

[bundle overlay]: https://juju.is/docs/charm-bundles#heading--overlay-bundles
