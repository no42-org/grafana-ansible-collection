.DEFAULT_GOAL:= lint
# No PATH manipulation. Every script that needs a Node binary names it
# explicitly as ./node_modules/.bin/<tool>, and no recipe here calls one bare,
# so prepending node_modules to PATH only made it ambiguous which copy of a
# tool a recipe would get. The inherited `PATH := ./node_modules/.bin:$(PATH)`
# line is gone.
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

# Provisions both toolchains. `uv sync` installs the pinned Python linters into
# .venv, provisioning an interpreter if the machine has none that fits -- which
# is the whole reason pipenv was replaced. `yarn install` provides the Node
# linters.
# Provisions both toolchains. `corepack yarn` uses the version pinned by
# package.json's packageManager field, rather than whatever yarn the machine
# happens to provide. `uv sync` installs the pinned Python linters into .venv,
# provisioning an interpreter if the machine has none that fits -- which is the
# whole reason pipenv was replaced.
install:
	corepack enable
	yarn install
	uv sync --group lint

# remove the build and log folders
clean:
	rm -rf build node_modules

####################################################################
#                          Role tests                              #
####################################################################

# Run a role test: converge, idempotence, verify — against a container.
# Replaces the Molecule workflows; depends only on uv and docker. ansible-core
# comes from pyproject.toml's `ansible` group, the same version CI runs.
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

# Compares each role's pinned version against the upstream project's latest
# release. Fails if a pin is unreadable or an upstream lookup does not resolve
# -- "could not look" must not read as "nothing to do".
role-versions-check:
	@python3 tools/check-role-versions.py

# Opens one pull request per behind role, from the report the check writes.
# Never merges: the bump is verified by the role tests first.
role-versions-bump:
	@./tools/bump-role-versions.sh

# Release machinery linting: tools/*.sh, galaxy.yml, dependabot.yml and every
# workflow's hygiene. It is deliberately NOT the full ci-lint set, and the
# reason changed with honest-ci-gates.
#
# The old reason was false: "ci-lint is red on a pristine tree from inherited
# findings, and fixing those would break the upstream-merge property." The
# findings were real -- 61 yamllint errors, 14 ansible-lint, 5 editorconfig --
# but they are all fixed now, and fixing them cost four newly-diverging files
# of whitespace, not the merge property.
#
# The remaining reason is only about what this one target covers, not about
# what a release checks. `honest-ci-gates` claimed the pipenv toolchain made
# the full set too fragile for the release path; that was wrong. `make install`
# has succeeded on every CI run, because setup-python supplies the Python 3.10
# that Pipfile pins. The fragility is local, on a machine without that
# interpreter, and CI never had it.
#
# So the full set does gate a release, via .github/workflows/gate.yml, which
# both ci.yml and release.yml call. This target stays narrow because it is the
# release *machinery* check -- tools/*.sh and the workflows -- and it is useful
# precisely because it needs no provisioned toolchain, so it runs in seconds
# locally.
ci-lint-release:
	@./tools/lint-release.sh
