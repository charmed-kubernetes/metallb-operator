CHANNEL ?= unpublished
CHARM_BUILD_DIR ?= ./build

setup-env:
	@bash script/bootstrap

charms: setup-env
	@env CHARM=metallb-controller CHARM_BUILD_DIR=$(CHARM_BUILD_DIR) bash script/build
	@env CHARM=metallb-speaker CHARM_BUILD_DIR=$(CHARM_BUILD_DIR) bash script/build

charm: setup-env
ifndef CHARM
	$(error CHARM is not set)
endif
	@env CHARM=$(CHARM) CHARM_BUILD_DIR=$(CHARM_BUILD_DIR) bash script/build

upload: setup-env
ifndef CHARM
	$(error CHARM is not set)
endif
ifndef NAMESPACE
	$(error NAMESPACE is not set)
endif

	@env CHARM=$(CHARM) NAMESPACE=$(NAMESPACE) CHANNEL=$(CHANNEL) CHARM_BUILD_DIR=$(CHARM_BUILD_DIR) bash script/upload

update:
	@bash script/update

.phony: charms charm upload setup-env update
all: charm
