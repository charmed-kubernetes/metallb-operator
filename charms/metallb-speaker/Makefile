PYTHON := /usr/bin/python3

PROJECTPATH=$(dir $(realpath $(MAKEFILE_LIST)))
ifndef CHARM_BUILD_DIR
	CHARM_BUILD_DIR=${PROJECTPATH}.build
endif
METADATA_FILE="metadata.yaml"
CHARM_NAME=$(shell cat ${PROJECTPATH}/${METADATA_FILE} | grep -E '^name:' | awk '{print $$2}')

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
    # `charmcraft build` currently does not work on ubuntu bionic (bug: https://github.com/canonical/charmcraft/issues/102)
	@echo "Building charm to base directory ${CHARM_BUILD_DIR}"
	@mkdir -p ${CHARM_BUILD_DIR}/
	@charmcraft build
	@mv ${CHARM_NAME}.charm ${CHARM_BUILD_DIR}/.

# bypassing bug https://github.com/canonical/charmcraft/issues/109
unpack: build
	@mkdir -p ${CHARM_BUILD_DIR}/${CHARM_NAME}
	@echo "Unpacking built .charm into ${CHARM_BUILD_DIR}/${CHARM_NAME}"
	@cd ${CHARM_BUILD_DIR}/${CHARM_NAME} && unzip -q ${CHARM_BUILD_DIR}/${CHARM_NAME}.charm

release: clean build unpack
	@echo "Charm is built at ${CHARM_BUILD_DIR}/${CHARM_NAME}"

lint:
	@echo "Running lint checks"
	@tox -e lint

proof:
	@echo "Running charm proof"
	@echo "Some warnings in charm proof do not apply to Operator charms."
	@-charm proof

unittests:
	@echo "Running unit tests"
	@tox -e unit

functional: build
	@echo "Executing functional tests in ${CHARM_BUILD_DIR}"
	@CHARM_BUILD_DIR=${CHARM_BUILD_DIR} tox -e func

test: lint proof unittests functional
	@echo "Tests completed for charm ${CHARM_NAME}."

#section for dev only
deploy: build
	@juju deploy ./.build/${CHARM_NAME}.charm

clean-app:
	@juju remove-application ${CHARM_NAME}

clean-app-force:
	@juju remove-application ${CHARM_NAME} --force --no-wait

# The targets below don't depend on a file
.PHONY: help submodules clean build release lint proof unittests functional test
