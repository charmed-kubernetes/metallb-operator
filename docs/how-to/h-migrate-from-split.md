# How to Migrate from Split

With the charms available through `1.27/stable` channels, one would typically create a model named `metallb-system` and deploy the 2 charms (`metallb-controller` and `metallb-speaker`) into that model, since juju maps a model name into a kubernetes namespace. While operating in this namespace isn't a hard requirement for metallb, it is the suggested namespace.

Starting in `1.28/stable`, this two charm deployment has been unified into a single charm which applies the upstream manifests into the system and manages those manifests, rather than directly managing the sidecar containers. The following is the process to use this new charm.

## Basic Steps
First create a new model (call it whatever is preferred) so long as it is not named `metallb-system` and deploy the charm into that model.

```shell
juju add-model juju-metallb
juju deploy metallb --channel 1.28/stable --trust --config namespace=metallb-system-2
```

Next, wait until the metallb charm is active/idle

```shell
juju status -m juju-metallb --watch=1s
```

Once stable, the new MetalLB installation will take over managing existing LoadBalancer services, and the model containing the old charms may be deleted.

```shell
juju switch metallb-system
juju remove-application metallb-speaker
juju remove-application metallb-controller
```

Once the model is empty, it should be safe to remove the model

```shell
juju destroy-model metallb-system --no-prompt
```
