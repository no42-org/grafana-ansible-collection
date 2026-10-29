.DEFAULT_GOAL:= lint
SHELL := /bin/bash
args = $(filter-out $@, $(MAKECMDGOALS))
.PHONY: all setup install clean reinstall build compile pdfs lint lint-sh lint-shell lint-md lint-markdown lint-txt lint-text pdf lint-yaml lint-yml lint-editorconfig lint-ec ci-lint ci-lint-shell ci-lint-markdown ci-lint-text ci-lint-yaml ci-lint-editorconfig lint-ansible ci-lint-ansible ci-lint-release carried-prs upstream-bootstrap upstream-sync upstream-status upstream-check-token role-test role-test-list module-test module-test-list sanity units version-select-test dist dist-clean handover-check handover-check-coverage handover-unit handover-rebuild handover-seed handover-matrix handover-test handover-promote handover-facts handover-render handover-push-candidates handover-publish-local

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

# Provisions the toolchain. `uv sync` installs the pinned linters into .venv,
# provisioning an interpreter if the machine has none that fits -- which is the
# whole reason pipenv was replaced. One toolchain: the Node one that carried
# markdownlint-cli2 and textlint is gone, see #137.
install:
	uv sync --group lint

# remove the build folder
clean:
	rm -rf build

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
#
# ANSIBLE_GROUP picks the pyproject.toml group that supplies ansible-core:
# `ansible` (default) or `ansible-top`, the newest inside requires_ansible.
ROLE ?=
DISTRO ?= debian
ANSIBLE_GROUP ?= ansible
VARIANT ?=

role-test:
	@if [ -z "$(ROLE)" ]; then \
		echo "usage: make role-test ROLE=<role> [DISTRO=debian|rhel] [ANSIBLE_GROUP=ansible|ansible-top] [VARIANT=<name>]"; \
		echo "       make role-test-list"; \
		exit 1; \
	fi
	@ROLE_TEST_ANSIBLE_GROUP=$(ANSIBLE_GROUP) ROLE_TEST_VARIANT=$(VARIANT) ./tools/role-test.sh $(ROLE) $(DISTRO)

role-test-list:
	@./tools/role-test.sh --list

####################################################################
#                         Module tests                             #
####################################################################

# Run a plugin module against a Grafana container: mint a token, run the
# scenario, assert the result in Grafana.
#
#   make module-test MODULE=datasource
#
# The role tests cover roles/. This covers plugins/, whose behaviour is which
# HTTP route the module builds -- the thing upstream #537 got wrong when
# Grafana 13.0 removed `PUT /api/datasources/:id`. Only a real Grafana can
# report which routes it serves, so the harness starts one, on the version
# roles/grafana/defaults/main.yml pins.
#
# Distinct from tests/integration/targets/, which is inherited, written for
# `ansible-test integration` against a Grafana Cloud stack, and dormant.
MODULE ?=

module-test:
	@if [ -z "$(MODULE)" ]; then \
		echo "usage: make module-test MODULE=<module>"; \
		echo "       make module-test-list"; \
		./tools/module-test.sh --list; \
		exit 1; \
	fi
	@./tools/module-test.sh $(MODULE)

module-test-list:
	@./tools/module-test.sh --list

# ansible-test sanity, against a tree staged the way CI shapes it.
#
# The staging is the point. ansible-test refuses to run outside
# ansible_collections/<namespace>/<name>, so a local run has to copy the tree
# somewhere first, and copying the wrong subset produces a green run against
# files CI does not have. That happened once, with the dist exclude list; see
# the header of tools/ansible-test.sh.
sanity:
	@./tools/ansible-test.sh sanity $(args)

# ansible-test units, against the same staged tree as sanity. A module whose
# endpoint is a hosted service, such as cloud_plugin and https://grafana.com,
# is out of reach of module-test's container, so its HTTP calls are mocked here.
units:
	@./tools/ansible-test.sh units $(args)

# Cover the `<role>_version: latest` resolution against recorded GitHub
# payloads. No container and no network: the role tests all pin their version,
# so `when: <role>_version == "latest"` never fires there, and pointing a test
# at the live API would make it depend on what upstream published this hour --
# which is the input the selection exists to defend against. See
# tests/version-selection/verify.yml and upstream issue #530.
version-select-test:
	@uv run --frozen --group ansible ansible-playbook tests/version-selection/verify.yml

####################################################################
#                       Upstream curation                          #
####################################################################

# Report the upstream pull requests this fork carries ahead of upstream, and
# which of them upstream has since merged and can therefore be dropped.
carried-prs:
	@./tools/carried-prs.sh

# The candidate set: what upstream has open that this fork has not acted on.
# carried-prs answers the opposite question -- what is already here -- and the
# two never overlap. See tools/upstream-tracker.sh.
#
# Run once per board, or after adding a field to FIELD_SPECS.
upstream-bootstrap:
	@./tools/upstream-tracker.sh --bootstrap

# Add what upstream opened, refresh what it closed or merged. Never writes the
# Fork decision or Target release fields, so it is safe to re-run at any time.
upstream-sync:
	@./tools/upstream-tracker.sh

# The board as a table, without asking upstream anything.
upstream-status:
	@./tools/upstream-tracker.sh --report

# Confirm the token can still write the board. Writes nothing. The scheduled
# job's pre-flight: a secret that exists is not a secret that still works.
upstream-check-token:
	@./tools/upstream-tracker.sh --check-token

####################################################################
#                          Distribution                            #
####################################################################

# Build the publishable collection tarball.
#
# The tree is copied to build/src and the namespace rewrite happens there, so
# the working tree is never modified and upstream merges stay conflict-free.
# tools/rename-namespace.sh owns the exclude list, asked for via
# --rsync-excludes, so the copy and the rewrite cannot disagree on scope.
# ansible-galaxy comes from pyproject.toml's `ansible` group, so the artifact
# is built by the ansible-core the gates and role tests run on.
dist: dist-clean
	@mkdir -p $(DIST_SRC) $(DIST_OUT)
	rsync -a $$(./tools/rename-namespace.sh --rsync-excludes) ./ $(DIST_SRC)/
	./tools/rename-namespace.sh $(GALAXY_NAMESPACE) $(DIST_SRC)
	uv run --frozen --group ansible ansible-galaxy collection build $(DIST_SRC) --output-path $(DIST_OUT)
	@ls -1 $(DIST_OUT)/*.tar.gz

# remove only the dist output, leaving .venv in place
dist-clean:
	rm -rf $(BUILD_DIR)

# start over from a clean build directory and a fresh toolchain sync
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
# both ci.yml and galaxy-release.yml call. This target stays narrow because it is the
# release *machinery* check -- tools/*.sh and the workflows -- and it is useful
# precisely because it needs no provisioned toolchain, so it runs in seconds
# locally.
ci-lint-release:
	@./tools/lint-release.sh

####################################################################
#                   Upstream handover                              #
####################################################################
# The manifest in tools/handover/chunks.yml, validated. Coverage is separate
# because a squash merge changes shas and a commit cannot list itself.
HANDOVER_PY := uv run --frozen --group ansible python
# The ref the manifest's commits must be on. A pull request checkout has no
# local main, only origin/main, so the gate sets this.
HANDOVER_MAIN ?= main

handover-check:
	@$(HANDOVER_PY) tools/handover/handover.py check --main $(HANDOVER_MAIN)

handover-check-coverage:
	@$(HANDOVER_PY) tools/handover/handover.py check --coverage

handover-unit:
	@$(HANDOVER_PY) -m unittest discover -s tools/handover/tests -t tools/handover -v

# Rebase each review branch onto upstream into a local handover-candidate
# branch, parents first, and write build/handover/state.json. Never pushes.
handover-rebuild:
	@$(HANDOVER_PY) tools/handover/handover.py rebuild $(args)

# The CI test matrix for the rebuilt candidates, as GitHub Actions JSON.
handover-matrix:
	@$(HANDOVER_PY) tools/handover/handover.py matrix

# Build one chunk's first review branch by cherry-picking its commits, one
# chunk at a time. A conflict stops it; resolve, then rerun with CONTINUE=1.
# Never pushes.
handover-seed:
	@if [ -z "$(CHUNK)" ]; then \
		echo "usage: make handover-seed CHUNK=<chunk id> [CONTINUE=1]"; \
		exit 1; \
	fi
	@$(HANDOVER_PY) tools/handover/handover.py seed --chunk $(CHUNK) $(if $(CONTINUE),--continue)

# Run one chunk's declared tests in TREE (default: this checkout). CI checks
# the candidate out into a subdirectory, because the candidate is upstream
# plus the chunk and does not contain this tooling.
TREE ?= .
handover-test:
	@if [ -z "$(CHUNK)" ]; then \
		echo "usage: make handover-test CHUNK=<chunk id> [TREE=<path>]"; \
		exit 1; \
	fi
	@$(HANDOVER_PY) tools/handover/handover.py test --chunk $(CHUNK) --tree $(TREE)

# Force-push the rebuilt candidates to handover-candidate/* on origin, through
# the same vetted push URL as promote, so CI can test them.
handover-push-candidates:
	@$(HANDOVER_PY) tools/handover/handover.py push-candidates $(args)

# Push candidates that passed to review/* on origin. Never touches upstream.
handover-promote:
	@$(HANDOVER_PY) tools/handover/handover.py promote $(args)

# Commits, landed state, CLA status and board rows for the page, into
# build/handover/facts.json. Read-only against GitHub.
handover-facts:
	@$(HANDOVER_PY) tools/handover/handover.py facts $(args)

# The page, from the manifest, state.json and facts.json, into
# build/handover/site/index.html with state.json beside it. Never publishes.
handover-render:
	@$(HANDOVER_PY) tools/handover/handover.py render $(args)

# Rebuild, facts and render for local inspection. Pushes nothing. A rebuild
# that conflicted still wrote the state file and the page shows the conflict;
# one that could not run wrote none, and that stops here.
handover-publish-local:
	@rm -f $(BUILD_DIR)/handover/state.json
	@$(HANDOVER_PY) tools/handover/handover.py rebuild || test -f $(BUILD_DIR)/handover/state.json
	@$(HANDOVER_PY) tools/handover/handover.py facts
	@$(HANDOVER_PY) tools/handover/handover.py render
