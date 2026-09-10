#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Editorconfig Linting using editorconfig-checker"

source "./tools/includes/editorconfig-checker.sh"

source "./tools/includes/lint-paths.sh"

if ! ecBin="$(editorconfigCheckerBin)"; then
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# Checks the files git tracks, not the whole tree. The previous invocation
# walked everything with one -exclude regex and so reported on .venv/,
# node_modules/, build/src/ and the AI tool directories -- code this
# repository does not own. See tools/includes/lint-paths.sh.
#
# LICENSE, *.txt and *.py stay excluded, as before: the first is upstream's
# verbatim licence text and the last two are checked by ansible-test sanity.
# Filtering with git's own exclude pathspecs rather than `grep -z`: on this
# maintainer's machine `grep` is ugrep, where -z means "search compressed
# files" rather than "NUL-separated records". The pipeline silently produced
# one newline-joined blob, `xargs -0` passed it as a single bogus filename, and
# the gate reported success over a file with trailing whitespace. Exactly the
# defect this script was being rewritten to fix.
statusCode=0
git ls-files -z -- ':!:LICENSE' ':!:*.txt' ':!:*.py' \
  | xargs -0 "${ecBin}"
currentCode="$?"
# only override the statusCode if it is 0
if [[ "$statusCode" == 0 ]]; then
  statusCode="$currentCode"
fi

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
