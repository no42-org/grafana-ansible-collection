#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

source "./tools/includes/lint-paths.sh"

# output the heading
heading "Grafana Ansible Collections" "Performing Text Linting using textlint"

# check to see if remark is installed
if [[ ! -f "$(pwd)"/node_modules/.bin/textlint ]]; then
  emergency "remark node module is not installed, please run: make install";
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# One invocation over the prose this fork authors, scoped exactly as
# tools/lint-markdown.sh is and for the same reason: the top-level README, the
# role READMEs and examples/ are upstream's documents, and this fork does not
# reformat inherited files. See the comment there.
#
# Also one invocation rather than one per file: the per-file loop kept only the
# first non-zero status, which is the same hidden-total defect lint-markdown.sh
# had.
statusCode=0
if ! git ls-files -z -- '*.md' \
        ':!:README.md' ':!:roles/*/README.md' ':!:examples/*.md' ':!:CLAUDE.md' \
      | xargs -0 "$(pwd)"/node_modules/.bin/textlint --config "$(pwd)/.textlintrc"; then
  statusCode=1
fi

echo ""
echo ""

# if the script was called by another, send a valid exit code
if [[ "$sourced" == "1" ]]; then
  return "$statusCode"
else
  exit "$statusCode"
fi
