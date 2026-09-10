.DEFAULT_GOAL:= lint
PATH := ./node_modules/.bin:$(PATH)
SHELL := /bin/bash
args = $(filter-out $@, $(MAKECMDGOALS))
.PHONY: all setup install clean reinstall build compile pdfs lint lint-sh lint-shell lint-md lint-markdown lint-txt lint-text pdf lint-yaml lint-yml lint-editorconfig lint-ec ci-lint ci-lint-shell ci-lint-markdown ci-lint-text ci-lint-yaml ci-lint-editorconfig lint-ansible ci-lint-ansible role-test role-test-list

default: all

all: install

####################################################################
#                   Installation / Setup                           #
####################################################################
setup:
	@./tools/setup.sh

install:
	yarn install
	pipenv install

# remove the build and log folders
clean:
	rm -rf build node_modules

####################################################################
#                          Role tests                              #
####################################################################

# Run a role test: converge, idempotence, verify — against a container.
# Replaces the Molecule workflows; depends only on ansible-core and docker.
#
#   make role-test ROLE=grafana DISTRO=rhel
#
# DISTRO is a family, not a distribution. The rhel entry is not symmetry: the
# grafana role's yum/dnf block, and the carried fixes inside it, are
# unreachable on Debian.
ROLE ?=
DISTRO ?= debian

role-test:
	@if [ -z "$(ROLE)" ]; then \
		echo "usage: make role-test ROLE=<role> [DISTRO=debian|rhel]"; \
		echo "       make role-test-list"; \
		exit 1; \
	fi
	@./tools/role-test.sh $(ROLE) $(DISTRO)

role-test-list:
	@./tools/role-test.sh --list

# reinstall the node_modules and start with a fresh node build
reinstall: clean install

####################################################################
#                           Linting                                #
####################################################################
lint: lint-shell lint-markdown lint-text lint-yaml lint-editorconfig lint-ansible

# Note "|| true" is added to locally make lint can be ran and all linting is preformed, regardless of exit code

# Shell Linting
lint-sh lint-shell:
	@./tools/lint-shell.sh || true

# Markdown Linting
lint-md lint-markdown:
	@./tools/lint-markdown.sh || true

# Text Linting
lint-txt lint-text:
	@./tools/lint-text.sh || true

# Yaml Linting
lint-yml lint-yaml:
	@./tools/lint-yaml.sh || true

# Editorconfig Linting
lint-ec lint-editorconfig:
	@./tools/lint-editorconfig.sh || true

# Ansible Linting
lint-ansible:
	@./tools/lint-ansible.sh || true

####################################################################
#                              CI                                  #
####################################################################
ci-lint: ci-lint-shell ci-lint-markdown ci-lint-text ci-lint-yaml ci-lint-editorconfig ci-lint-ansible ci-lint-versions

# Shell Linting
ci-lint-shell:
	@./tools/lint-shell.sh

# Markdown Linting
ci-lint-markdown:
	@./tools/lint-markdown.sh

# Text Linting
ci-lint-text:
	@./tools/lint-text.sh

# Yaml Linting
ci-lint-yaml:
	@./tools/lint-yaml.sh

# The versions the documentation claims against the versions the roles pin.
# Needs no toolchain and no network: it reads defaults/main.yml and the
# READMEs. Run tools/check-documented-versions.py --fix to rewrite the claims.
ci-lint-versions:
	@python3 tools/check-documented-versions.py

# Editorconfig Linting
ci-lint-editorconfig:
	@./tools/lint-editorconfig.sh

# Ansible Linting
ci-lint-ansible:
	@./tools/lint-ansible.sh

# Compares each role's pinned version against the upstream project's latest
# release. Fails if a pin is unreadable or an upstream lookup does not resolve
# -- "could not look" must not read as "nothing to do".
role-versions-check:
	@python3 tools/check-role-versions.py

# Opens one pull request per behind role, from the report the check writes.
# Never merges: the bump is verified by the role tests first.
role-versions-bump:
	@./tools/bump-role-versions.sh
