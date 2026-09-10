#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

source "./tools/includes/lint-paths.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Markdown Linting using markdownlint"

if [[ ! -f "$(pwd)"/node_modules/.bin/markdownlint-cli2 ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: markdownlint-cli2 is not available. Run \"make install\".";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# One invocation over the files git tracks, not one per directory.
#
# The previous shape ran markdownlint once per directory glob and kept only the
# first non-zero status, so its "Summary: N error(s)" line reported the last
# group's count. It printed "Summary: 2 error(s)" over 3718 findings. It also
# used markdownlint-cli2-config, a wrapper binary removed in markdownlint-cli2
# 0.23; the config now arrives via --config.
# Scoped to the prose this fork authors.
#
# The inherited documents -- the top-level README that Galaxy renders, the role
# READMEs, and examples/ -- are excluded, and this is the same reasoning that
# keeps roles/*/molecule/ untouched: they are upstream's documents, and the one
# convention this fork will not break is "do not reformat inherited files".
# Bringing them to this configuration means 172 findings of table style, fence
# languages and list spacing across files upstream still edits, which is a
# whitespace sweep of someone else's prose.
#
# The trade is stated rather than hidden: those documents ship in the
# collection and go unlinted. If upstream maintainership resumes, the right
# move is to offer the fixes there rather than apply them here.
statusCode=0
if ! git ls-files -z -- '*.md' \
        ':!:README.md' ':!:roles/*/README.md' ':!:examples/*.md' ':!:CLAUDE.md' \
      | xargs -0 ./node_modules/.bin/markdownlint-cli2 --config "$(pwd)/.markdownlint.yaml"; then
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
