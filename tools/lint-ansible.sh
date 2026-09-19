#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"
source "$(pwd)/tools/includes/galaxy.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Ansible Linting using ansible-lint"

# The toolchain not being installed is a distinct failure from the linter
# finding something, and the messages say which.
if [[ "$(command -v uv)" = "" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: uv is required, see (https://docs.astral.sh/uv/) or run: brew install uv";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

# The probe is `--version`, which ansible-lint answers only after loading the
# config it discovers in the working directory. So a config it rejects fails the
# probe exactly like a missing binary, and reporting that as "not installed"
# sends the reader to `make install`, which cannot fix it. Both states are real
# and neither is a lint finding, so they are told apart by what the probe said.
if ! probe="$(uv run --frozen --group lint ansible-lint --version 2>&1)"; then
  if grep -qi "invalid configuration" <<< "${probe}"; then
    echo >&2 "CONFIG INVALID: ansible-lint refused .ansible-lint.";
    echo >&2 "${probe}";
    echo >&2 "This is not a lint failure and not a missing toolchain. No file has been checked.";
  else
    echo >&2 "TOOLCHAIN NOT INSTALLED: ansible-lint is not available. Run \"make install\".";
    echo >&2 "This is not a lint failure. No file has been checked.";
  fi
  exit 1;
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# Install the collections first, then lint with --offline, in that order and
# for that reason.
#
# ansible-lint installs requirements.yml itself, with no retry, which is how an
# HTTP 502 from Galaxy failed "Gate / Lint the collection" outright -- a gate
# the release pipeline runs. galaxyInstall retries; ansible-lint then reads
# what is already on disk and opens no socket of its own.
#
# The order is the safety property, not a preference. `ansible-lint --offline`
# on a tree with no collections installed exits 0 and reports a clean pass, so
# it is only sound when something has already guaranteed the collections are
# there. galaxyInstall exits the script if it cannot, which is what makes the
# guarantee. Reversing these two lines would turn this into the defect it
# prevents.
#
# No offline probe here: requirements.yml names its collections by git URL, and
# those are re-cloned whatever --offline says.
GALAXY_CMD=(uv run --frozen --group lint ansible-galaxy)
galaxyInstall "$(pwd)/requirements.yml"

# run ansible-lint
echo "$(pwd)/.ansible-lint"
uv run --frozen --group lint ansible-lint --offline --config-file "$(pwd)/.ansible-lint" --strict
statusCode="$?"

if [[ "$statusCode" == "0" ]]; then
  echo "no issues found"
  echo ""
fi

echo ""
# if the script was called by another, send a valid exit code
if [[ "$sourced" == "1" ]]; then
  return "$statusCode"
else
  exit "$statusCode"
fi
