#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Ansible Linting using ansible-lint"

# make sure pipenv exists
if [[ "$(command -v pipenv)" = "" ]]; then
  echo >&2 "pipenv command is required, see (https://pipenv.pypa.io/en/latest/) or run: brew install pipenv";
  exit 1;
fi

# make sure yamllint exists
if [[ "$(pipenv run pip freeze | grep -c "ansible-lint")" == "0" ]]; then
  echo >&2 "ansible-lint command is required, see (https://pypi.org/project/ansible-lint/). Run \"make install\" to install it.";
  exit 1;
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# This collection, resolvable by its own name.
#
# ansible-lint syntax-checks every playbook, and a playbook that calls
# grafana.grafana.<module> can only be checked if that name resolves to
# <path>/ansible_collections/grafana/grafana. The repository *is* that
# collection without being laid out as one, so nothing here resolved it and
# tests/modules/datasource/verify.yml failed in CI with "couldn't resolve
# module/action" while passing locally -- on a machine whose .ansible/ happened
# to hold a copy installed months earlier. That copy is the worse half of the
# defect: stale content shadowing the working tree, deciding a gate.
#
# A symlink rather than a copy, for the same reason tools/module-test.sh uses
# one: the tree is what should be linted. It lives under build/, which
# .gitignore excludes and ansible-lint honours, so it is a path to read from
# and never a file to lint.
#
# ANSIBLE_COLLECTIONS_PATH replaces the default search list rather than adding
# to it, which is what stops ~/.ansible and ./.ansible from shadowing. The
# repository root stays on it because ansible.cfg's `collections_path = ./` is
# where galaxyInstall above puts the dependency collections.
lintNamespace="$(awk '/^namespace:/ {print $2; exit}' galaxy.yml | tr -d '"'"'"'')"
lintName="$(awk '/^name:/ {print $2; exit}' galaxy.yml | tr -d '"'"'"'')"
if [[ -z "${lintNamespace}" || -z "${lintName}" ]]; then
  echo >&2 "could not read namespace/name from galaxy.yml";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi
lintCollections="$(pwd)/build/lint/collections"
rm -rf "${lintCollections}"
mkdir -p "${lintCollections}/ansible_collections/${lintNamespace}"
ln -s "$(pwd)" "${lintCollections}/ansible_collections/${lintNamespace}/${lintName}"
ANSIBLE_COLLECTIONS_PATH="${lintCollections}:$(pwd)"
export ANSIBLE_COLLECTIONS_PATH

# run yamllint
echo "$(pwd)/.ansible-lint"
pipenv run ansible-lint --config-file "$(pwd)/.ansible-lint" --strict
statusCode="$?"

if [[ "$statusCode" == "0" ]]; then
  echo "no issues found"
  echo ""
fi

echo ""
# if the script was called by another, send a valid exit code
if [[ "$sourced" == "1" ]]; then
  return "$statusCode"
fi
