# MetalLB Charm

## Description

The MetalLB charm offers a software network load balancing implementation that allows
for LoadBalancing services in Kubernetes. 

Upstream documentation can be found here : <https://metallb.universe.tf/>


## Usage

`juju deploy charm-metallb`

### Scale Out Usage

`add info here`

## Developing

Create and activate a virtualenv,
and install the development requirements,

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev

## Testing

Just run `run_tests`:

    ./run_tests
