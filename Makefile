.DEFAULT_GOAL:= lint
PATH := ./node_modules/.bin:$(PATH)
SHELL := /bin/bash
args = $(filter-out $@, $(MAKECMDGOALS))
.PHONY: all setup install clean reinstall build compile pdfs lint lint-sh lint-shell lint-md lint-markdown lint-txt lint-text pdf lint-yaml lint-yml lint-editorconfig lint-ec ci-lint ci-lint-shell ci-lint-markdown ci-lint-text ci-lint-yaml ci-lint-editorconfig lint-ansible ci-lint-ansible ci-lint-release carried-prs role-test role-test-list dist dist-clean

# Galaxy namespace this fork publishes to. The working tree keeps saying
# "grafana", and the rename happens in build/src at dist time.
GALAXY_NAMESPACE := indigo423
BUILD_DIR := build
DIST_SRC := $(BUILD_DIR)/src
DIST_OUT := $(BUILD_DIR)/dist

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

####################################################################
#                       Upstream curation                          #
####################################################################

# Report the upstream pull requests this fork carries ahead of upstream, and
# which of them upstream has since merged and can therefore be dropped.
carried-prs:
	@./tools/carried-prs.sh

####################################################################
#                          Distribution                            #
####################################################################

# Build the publishable collection tarball.
#
# The tree is copied to build/src and the namespace rewrite happens there, so
# the working tree is never modified and upstream merges stay conflict-free.
# tools/rename-namespace.sh owns the exclude list, asked for via
# --rsync-excludes, so the copy and the rewrite cannot disagree on scope.
dist: dist-clean
	@mkdir -p $(DIST_SRC) $(DIST_OUT)
	rsync -a $$(./tools/rename-namespace.sh --rsync-excludes) ./ $(DIST_SRC)/
	./tools/rename-namespace.sh $(GALAXY_NAMESPACE) $(DIST_SRC)
	cd $(DIST_SRC) && ansible-galaxy collection build --output-path ../../$(DIST_OUT)
	@ls -1 $(DIST_OUT)/*.tar.gz

# remove only the dist output, leaving node_modules in place
dist-clean:
	rm -rf $(BUILD_DIR)

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
ci-lint: ci-lint-shell ci-lint-markdown ci-lint-text ci-lint-yaml ci-lint-editorconfig ci-lint-ansible

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

# Editorconfig Linting
ci-lint-editorconfig:
	@./tools/lint-editorconfig.sh

# Ansible Linting
ci-lint-ansible:
	@./tools/lint-ansible.sh

# Release machinery linting: the subset of ci-lint that gates a release.
# ci-lint itself is red on a pristine tree from inherited upstream findings, and
# fixing those would break the upstream-merge property this fork depends on.
ci-lint-release:
	@./tools/lint-release.sh
