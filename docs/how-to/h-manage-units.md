# How to deploy and manage units

## Basic Usage

To deploy a single unit of MetalLB using its default configuration

```shell
juju deploy metallb --channel 1.28/stable --trust
```

## Removing MetalLB

To remove MetalLB, ending any LoadBalanced services it provides, you may remove the application from its model

```shell
juju remove-application metallb
```
