The Charmed MetalLB Operator delivers automated operations management from day 0 to day 2
on the [MetalLB Load Balancer Implementation for Bare Metal Kubernetes](https://metallb.universe.tf/).
It is an open source, production-ready charm on top of [Juju](https://juju.is/)

MetalLB is a load-balancer implementation for bare metal Kubernetes clusters, using standard routing protocols.

The Charmed MetalLB Operator provides Layer 2 (with ARP [Address Resolution Protocol](https://en.wikipedia.org/wiki/Address_Resolution_Protocol)) or BGP([Border Gateway Protocol](https://en.wikipedia.org/wiki/Border_Gateway_Protocol)) to expose services.

MetalLB has support for local traffic, meaning that the machine that receives the data will be the machine that services the request. It is not suggested to use a virtual IP with high traffic workloads because only one machine will receive the traffic for a service - the other machines are solely used for failover.

BGP does not have this limitation but does see nodes as the atomic unit. This means if the service is running on two of five nodes then only those two nodes will receive traffic, but they will each receive 50% of the traffic even if one of the nodes has three pods and the other only has one pod running on it. It is recommended to use node anti-affinity to prevent Kubernetes pods from stacking on a single node.

[note type="important" status="Note"]
For more information on configuring MetalLB with Calico in BGP mode, please see this [explanation of the required configuration](https://metallb.universe.tf/configuration/calico/) from the [MetalLB website](https://metallb.universe.tf/)
[/note]


## In this documentation

|  |  |
|--|--|
| [Tutorials](/t/charmed-metallb-tutorial-overview/11359?channel=1.28/stable)</br>  Get started - a hands-on introduction to using Charmed Metallb operator for new users </br> |  [How-to guides](/t/charmed-metallb-how-to-managed-units/11363?channel=1.28/stable) </br> Step-by-step guides covering key operations and common tasks |
| [Reference](https://charmhub.io/metallb/actions?channel=1.28/stable) </br> Technical information - specifications, APIs, architecture | [Explanation](/t/charmed-metallb-explanation/####?channel=1.28/stable) </br> Concepts - discussion and clarification of key topics  |


# Navigation

| Level | Path                 | NavLink                                                                                         |
|-------|----------------------|-------------------------------------------------------------------------------------------------|
| 1     | tutorial             | [Tutorial]()                                                                                    |
| 2     | t-overview           | [1. Introduction](/t/charmed-metallb-tutorial-overview/11359)                                   |
| 2     | t-setup-environment  | [2. Set up the environment](/t/charmed-metallb-tutorial-setup-environment/11360)                |
| 2     | t-deploy-metallb     | [3. Deploy MetalLB](/t/charmed-metallb-tutorial-deploy-metallb/11361)                           |
| 2     | t-configure          | [4. Configure MetalLB](/t/charmed-metallb-tutorial-configure/11362)                             |
| 1     | how-to               | [How To]()                                                                                      |
| 2     | h-manage-units       | [1. Managed Units](/t/charmed-metallb-how-to-managed-units/11363)                               |
| 2     | h-migrate-from-split | [2. Migrate From 1.27 Release](/t/charmed-metallb-how-to-migrate-from-1-27-stable-charms/11423) |
| 1     | reference            | [Reference]()                                                                                   |
| 2     | r-actions            | [Actions](https://charmhub.io/metallb/actions)                                                  |
| 2     | r-configurations     | [Configurations](https://charmhub.io/metallb/configure)                                         |
| 2     | r-libraries          | [Libraries](https://charmhub.io/metallb/libraries)                                              |
| 2     | r-integrations       | [Integrations](https://charmhub.io/metallb/integrations)                                        |
| 1     | explanation          | [Explanation]()                                                                                 |

# Redirects

[details=Mapping table]
| Path | Location |
| ---- | -------- |
[/details]
