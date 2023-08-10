# Configuration

This is part of the [Charmed MetalLB Tutorial](/t/charmed-metalb-tutorial-overview/11359?channel=1.28/stable). Please refer to this page for more information and the overview of the content.

You will need to change the IP addresses allocated to MetalLB to suit your environment. The IP addresses can be specified as a range, such as “192.168.1.88-192.168.1.89”, or as a comma-separated list of pools in CIDR notation, such as “192.168.1.240/28, 10.0.0.0/28”.

Configuring the IP addresses can be done either at time of deployment via single-line config or later by changing the charm config via Juju.

This will adjust the default `IPAddressPool.spec.addresses` created by the charm according to the [specification](https://metallb.universe.tf/configuration/_advanced_ipaddresspool_configuration/)

An example single-line config adjustment might look like:

```shell
juju deploy metallb --config iprange='192.168.1.88-192.168.1.89' --trust
```

Alternatively, you can change the config directly on the metallb charm at any time:

```shell
juju config metallb iprange="192.168.1.240/28, 10.0.0.0/28"
```

