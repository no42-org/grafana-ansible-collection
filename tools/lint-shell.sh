#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

source "./tools/includes/lint-paths.sh"

source "./tools/includes/provision.sh"
source "./tools/includes/shellcheck.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Shell Linting using shellcheck"

# The pinned, checksum-verified shellcheck, not whatever is on PATH. An ambient
# copy is a gate measuring a version nobody chose: this repository ran 0.11.0
# locally and 0.9.0 in CI for months, and neither side could have noticed.
if ! shellcheckCmd="$(shellcheckBin)"; then
  emergency "shellcheck could not be provisioned; see the message above";
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

statusCode=0
while read -r file; do
  "${shellcheckCmd}" \
    --external-sources \
    --shell bash \
    --source-path "$(dirname "$file")" \
    "$file"
  currentCode="$?"
  # if the current code is 0, output the file name for logging purposes
  if [[ "$currentCode" == 0 ]]; then
    echo -e "\\x1b[32m$file\\x1b[0m: no issues found"
  else
    echo ""
  fi
  # only override the statusCode if it is 0
  if [[ "$statusCode" == 0 ]]; then
    statusCode="$currentCode"
  fi
done < <(lintFind -type f -name "*.sh" -print)

echo ""
echo ""

# if the script was called by another, send a valid exit code
if [[ "$sourced" == "1" ]]; then
  return "$statusCode"
else
  exit "$statusCode"
fi
