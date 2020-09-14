PYTHON := /usr/bin/python3

# PROJECTPATH=$(dir $(realpath $(MAKEFILE_LIST)))
# ifndef CHARM_BUILD_DIR
# 	CHARM_BUILD_DIR=${PROJECTPATH}.build
# endif
# METADATA_FILE="metadata.yaml"
# CHARM_NAME=$(shell cat ${PROJECTPATH}/${METADATA_FILE} | grep -E '^name:' | awk '{print $$2}')

help:
	@echo "This project supports the following targets"
	@echo ""
	@echo " make help - show this text"
	@echo " make clean - remove unneeded files"
	@echo " make build - build the charm"
	@echo " make release - run clean and build targets"
	@echo " make lint - run flake8 and black"
	@echo " make proof - run charm proof"
	@echo " make unit - run the tests defined in the unittest subdirectory"
	@echo " make func - run the tests defined in the functional subdirectory"
	@echo " make test - run lint, proof, unittests and functional targets"
	@echo ""

clean:
	@echo "Cleaning files"
	@git clean -fXd
	@echo "Cleaning existing build"
	@rm -rf ${CHARM_BUILD_DIR}/${CHARM_NAME}

build:
    # builds all charms
	@echo "Building metallb-controller charm in directory charms/metallb-controller/.build"
	@mkdir -p charms/metallb-controller/.build
	@charmcraft build --from charms/metallb-controller
	@mv metallb-controller.charm charms/metallb-controller/.build/.
	@echo "Building metallb-speaker charm in directory charms/metallb-speaker/.build"
	@mkdir -p charms/metallb-speaker/.build
	@charmcraft build --from charms/metallb-speaker
	@mv metallb-speaker.charm charms/metallb-speaker/.build/.

# # bypassing bug https://github.com/canonical/charmcraft/issues/109
# unpack: build
# 	@mkdir -p ${CHARM_BUILD_DIR}/${CHARM_NAME}
# 	@echo "Unpacking built .charm into ${CHARM_BUILD_DIR}/${CHARM_NAME}"
# 	@cd ${CHARM_BUILD_DIR}/${CHARM_NAME} && unzip -q ${CHARM_BUILD_DIR}/${CHARM_NAME}.charm

# release: clean build unpack
# 	@echo "Charm is built at ${CHARM_BUILD_DIR}/${CHARM_NAME}"

# lint:
# 	@echo "Running lint checks"
# 	@tox -e lint

# proof:
# 	@echo "Running charm proof"
# 	@echo "Some warnings in charm proof do not apply to Operator charms."
# 	@-charm proof

# unittests:
# 	@echo "Running unit tests"
# 	@tox -e unit

# functional: build
# 	@echo "Executing functional tests in ${CHARM_BUILD_DIR}"
# 	@CHARM_BUILD_DIR=${CHARM_BUILD_DIR} tox -e func

# test: lint proof unittests functional
# 	@echo "Tests completed for charm ${CHARM_NAME}."

# The targets below don't depend on a file
.PHONY: help submodules clean build release lint proof unittests functional test
