#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Ansible Linting using ansible-lint"

# The toolchain not being installed is a distinct failure from the linter
# finding something, and the messages say which.
if [[ "$(command -v uv)" = "" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: uv is required, see (https://docs.astral.sh/uv/) or run: brew install uv";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

if ! uv run --frozen --group lint ansible-lint --version >/dev/null 2>&1; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: ansible-lint is not available. Run \"make install\".";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# run yamllint
echo "$(pwd)/.ansible-lint"
uv run --frozen --group lint ansible-lint --config-file "$(pwd)/.ansible-lint" --strict
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
