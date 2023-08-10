# Deployment

This is part of the [Charmed MetalLB Tutorial](/t/charmed-metalb-tutorial-overview/11359?channel=1.28/stable). Please refer to this page for more information and the overview of the content.

## Deploy Charmed MetalLB

To deploy Charmed MetaLB, all you need to do is 

The best way to deploy MetalLB in Layer 2 mode on Charmed Kubernetes is with the MetalLB charm, which activates
both the metallb controller Deployment and metallb speaker DaemonSet.

Run the following command, which will fetch the charm from [Charmhub](https://charmhub.io/metallb?channel=1.28/stable) and deploy it to your model:
```shell
juju deploy metallb --channel 1.28/stable --trust
```

Juju will now fetch Charmed MetalLB and begin deploying it to the Kubernetes cluster. This process can take several minutes depending on how provisioned (RAM, CPU, etc) your machine is. You can track the progress by running:

```shell
juju status --watch 1s
```

This command is useful for checking the status of Charmed MetalLB and gathering information about the containers hosting Charmed MetalLB. Some of the helpful information it displays include IP addresses, ports, state, etc. The command updates the status of Charmed MetalLB every second and as the application starts you can watch the status and messages of Charmed MetalLB change. Wait until the application is ready - when it is ready, `juju status` will show:
```
Model         Controller       Cloud/Region                     Version  SLA          Timestamp
juju-metallb  overlord         k8s-cloud/default                3.1.5    unsupported  13:32:58-05:00

App      Version  Status  Scale  Charm    Channel      Rev  Address        Exposed  Message
metallb           active      1  metallb  1.28/stable  9    10.152.183.85  no       

Unit        Workload  Agent  Address       Ports  Message
metallb/0*  active    idle   192.168.0.15         
```
To exit the screen with `juju status --watch 1s`, enter `Ctrl+c`.
If you want to further inspect juju logs, can watch for logs with `juju debug-log`.
More info on logging at [juju logs](https://juju.is/docs/olm/juju-logs).

