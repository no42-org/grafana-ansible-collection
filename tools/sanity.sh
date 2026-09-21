#!/usr/bin/env bash
#
# Run `ansible-test sanity` against a tree shaped the way CI shapes it.
#
# ansible-test requires the collection at ansible_collections/<namespace>/<name>
# and refuses to run anywhere else, so every local run has to stage a copy
# first. That staging step is the whole reason this script exists: get it wrong
# and the run is green against a tree CI does not have.
#
# It has been got wrong once, on 2026-09-21. The staging reused
# `tools/rename-namespace.sh --rsync-excludes`, which is the *distribution*
# exclude list -- it drops /tools, /.github, /Makefile and the fork-owned
# markdown because none of that ships in the tarball. Sanity therefore passed
# locally while CI failed pylint on tools/check-role-versions.py, a file the
# staged tree did not contain. The local log named no error because the local
# run had nothing to name.
#
# So the staged file list is asked of git rather than written out here: what
# git tracks, plus what is new and not ignored. If a file is in the repository
# CI lints it, and so does this; if it is not, neither does.
#
# It was a hand-written exclude list once, and that list was wrong in the other
# direction -- it omitted tools/bin, so 75 MB of downloaded linter binaries were
# staged, shipped into the container and read by the whole-file tests, none of
# which CI has ever seen. A fourth copy of tools/includes/lint-paths.sh is a
# fourth thing to keep in step; git already knows the answer.
#
# The namespace and name come from galaxy.yml rather than being written here
# again. `make dist` renames the namespace in a copy at build time, so the
# value in the tree is the source namespace CI checks out under, which is
# exactly what ansible-test needs.
#
# Usage: tools/sanity.sh [extra ansible-test arguments...]
#
#   tools/sanity.sh                     every sanity test
#   tools/sanity.sh --test pylint       one of them
#   tools/sanity.sh -v                  echo the commands, including file lists
#
# SANITY_KEEP=1 leaves the staged tree in place and prints where it is, for
# when a failure needs looking at rather than reproducing.
#
# ansible-core comes from pyproject.toml's `ansible` group, never from PATH,
# for the reason tools/role-test.sh gives at length: a local pass and a CI pass
# on different engines are statements about different software. CI additionally
# runs stable-2.17 and devel, which a pinned group cannot supply; this matches
# the middle leg, and the log says which.

set -o errexit
set -o pipefail
set -o nounset

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

heading "Grafana Ansible Collection" "Running ansible-test sanity"

if [[ "$(command -v uv)" = "" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: uv is required, see (https://docs.astral.sh/uv/) or run: brew install uv";
  exit 1;
fi
if [[ "$(command -v rsync)" = "" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: rsync is required to stage the collection tree";
  exit 1;
fi
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo >&2 "not a git repository: the staged file list is derived from git, not from the filesystem";
  exit 1;
fi
if ! docker info >/dev/null 2>&1; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: docker is required; ansible-test runs its tests in containers";
  exit 1;
fi

repoRoot="$(pwd)"
ansibleTest=(uv run --frozen --group ansible --project "${repoRoot}" ansible-test)

# The version line goes to the log on purpose, for the same reason role-test.sh
# prints one: a log that omits which engine ran cannot be compared with another.
if ! ansibleVersion="$(uv run --frozen --group ansible --project "${repoRoot}" ansible --version </dev/null 2>/dev/null | head -1)"; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: ansible-core is not available. Run \"make install\".";
  exit 1;
fi
info "engine: ${ansibleVersion} from dependency group 'ansible'"

# Read, not assumed. galaxy.yml is the one place the source namespace is stated.
namespace="$(awk '/^namespace:/ {print $2; exit}' "${repoRoot}/galaxy.yml" | tr -d '"'"'"'')"
name="$(awk '/^name:/ {print $2; exit}' "${repoRoot}/galaxy.yml" | tr -d '"'"'"'')"
if [[ -z "${namespace}" || -z "${name}" ]]; then
  echo >&2 "could not read namespace/name from galaxy.yml";
  exit 1;
fi
info "collection: ${namespace}.${name}"

stageRoot="$(mktemp -d)"
collectionDir="${stageRoot}/ansible_collections/${namespace}/${name}"

cleanup() {
  if [[ "${SANITY_KEEP:-0}" == "1" ]]; then
    info "SANITY_KEEP=1, leaving the staged tree at ${collectionDir}"
    return
  fi
  rm -rf "${stageRoot}"
}
trap cleanup EXIT

mkdir -p "${collectionDir}"

# tests/output is ansible-test's own scratch directory from a previous run in
# the working tree. Most of what lands there is ignored by .gitignore already,
# but not all of it, and carrying any of it in confuses the new run's
# bookkeeping -- hence the one pathspec exclusion git cannot infer.
info "staging the repository at ansible_collections/${namespace}/${name}"
fileList="${stageRoot}/files.txt"
git -C "${repoRoot}" ls-files -z --cached --others --exclude-standard \
  -- . ':(exclude)tests/output' >"${fileList}"
rsync -a --from0 --files-from="${fileList}" "${repoRoot}/" "${collectionDir}/"

staged="$(find "${collectionDir}" -type f | wc -l | tr -d ' ')"
tracked="$(tr -dc '\0' <"${fileList}" | wc -c | tr -d ' ')"
if [[ "${staged}" != "${tracked}" ]]; then
  echo >&2 "staged ${staged} file(s) but git listed ${tracked}; the staging step is not copying what it was told to";
  exit 1;
fi
info "staged ${staged} file(s) from git; tools/ and .github/ included, unlike the dist tree"

cd "${collectionDir}"
extra=("$@")
if "${ansibleTest[@]}" sanity --docker --color ${extra[@]+"${extra[@]}"}; then
  success "ansible-test sanity passed"
else
  status=$?
  error "ansible-test sanity failed"
  if [[ "${SANITY_KEEP:-0}" != "1" ]]; then
    info "re-run with SANITY_KEEP=1 to keep the staged tree for inspection"
  fi
  exit "${status}"
fi
