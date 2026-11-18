# MetalLB Operator

[![Get it from the Charmhub](https://charmhub.io/metallb/badge.svg)](https://charmhub.io/metallb)

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
`ghcr.io/canonical/cdk`. Note that this charm is workload-less, so there are no OCI-image resources associated with
it, as the charm simply applies a manifest via the Kubernetes API. You will need to use a registry that contains 
the speaker and controller images required by the upstream manifest. 

The `metallb-release` config option controls which bundled manifest to deploy.
The default is `v0.16.2`; `v0.13.10`, `v0.13.12`, `v0.14.9`, and `v0.15.3`
are also bundled. For Kubernetes 1.36, use `v0.16.2`: upstream fixed
[CRD ASN validation for Kubernetes 1.36](https://github.com/metallb/metallb/pull/3035)
in 0.16.0 and corrected the `BGPPeer.spec.localASN` schema in 0.16.1.
Older bundled versions do not include these fixes and are not CK 1.36 choices.

All bundles are unmodified upstream
[`metallb-native.yaml` release manifests](https://github.com/metallb/metallb/tree/v0.16.2/config/manifests).
The charm continues to configure Layer 2 using `IPAddressPool` and
`L2Advertisement` (`metallb.io/v1beta1`); it does not switch to the new Helm
chart's FRR-K8s default or deploy FRR sidecars. Images, namespaces, and node
selectors are still rewritten using the charm configuration.

The `iprange` config option specifies IP ranges and CIDRs that load-balancer services will consume. 
This should be a comma-separated list of hyphenated IP address ranges or CIDRs. 

### Upgrading MetalLB

Review the upstream [release notes](https://github.com/metallb/metallb/blob/v0.16.2/website/content/release-notes/_index.md)
before changing `metallb-release` or upgrading the charm. Back up the MetalLB
custom resources and record existing LoadBalancer IPs. Existing explicitly set
`metallb-release` values remain pinned; unset values follow the charm default.

- The old `AddressPool` API stopped allocating addresses in upstream v0.14.2 and
  its CRD is no longer deployed from v0.14.3 on. The charm itself only ever
  creates `IPAddressPool` and `L2Advertisement`, so its own pool is unaffected.
  Manually created `AddressPool` objects, however, would be left in place but
  inert. The charm therefore refuses to move a cluster whose controller still
  runs a release that serves `AddressPool` to one that does not while such
  objects exist in its namespace, and goes into a blocked state naming them. It
  never deletes them. Leftover objects do not block anything once the
  controller already runs a release without the API (the charm never prunes the
  old CRD), as they are inert at that point. To migrate, with `<ns>` being the
  charm's `namespace` option:

  ```
  kubectl get addresspools.metallb.io -n <ns> -o yaml
  # for each pool, create an equivalent IPAddressPool plus L2Advertisement
  # (or BGPAdvertisement), reusing spec.addresses:
  kubectl apply -f - <<EOF
  apiVersion: metallb.io/v1beta1
  kind: IPAddressPool
  metadata: {name: <name>, namespace: <ns>}
  spec: {addresses: [<addresses>]}
  ---
  apiVersion: metallb.io/v1beta1
  kind: L2Advertisement
  metadata: {name: <name>, namespace: <ns>}
  spec: {ipAddressPools: [<name>]}
  EOF
  kubectl delete addresspools.metallb.io <name> -n <ns>
  ```

  The unit re-checks on every `update-status` hook, so it applies the release and
  the configured pool by itself shortly after the last `AddressPool` object is
  gone; there is no need to change any configuration.
- `juju refresh` only applies the resources of the selected release and never
  prunes. The old `Service/webhook-service`, `Secret/webhook-server-cert` and the
  `addresspools.metallb.io` CRD (whose conversion webhook points at that now
  orphaned Service) therefore stay in the cluster after moving to 0.14.3 or later
  and are harmless; remove them manually once no `AddressPool` objects remain.
- In v0.16 the speaker, which uses host networking, serves metrics on port 9120
  and health probes on port 17472 of every node. Check for conflicts with other
  host-network workloads, notably on MicroK8s with strict confinement.
- `BGPPeer` v1beta1 is deprecated but still served, with v1beta2 as storage and
  a conversion webhook. Migrate manually managed peers to v1beta2; the charm
  itself does not create BGP peers. Keep the controller and its webhook
  reachable while the CRDs and configuration are reconciled.
- In 0.16.2 the memberlist encryption-key derivation changed. Old and new
  speakers cannot exchange gossip during the rolling update, so allow a
  maintenance window for transient L2 election changes and possible traffic
  disruption. Check that every speaker has updated before testing failover.
- Metrics in 0.16 use authenticated HTTPS on port 9120, rather than the old
  HTTP metrics endpoint. Update any external monitoring configuration.
- Removing or changing pools can reassign existing service IPs. Do not change
  `iprange` as part of the upgrade unless that is intentional. Confirm
  allocation, external connectivity, and failover after the rollout. A downgrade
  across CRD/schema changes is not a tested rollback; retain a backup and test
  recovery in an isolated environment first.

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
