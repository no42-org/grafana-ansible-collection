#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

source "./tools/includes/lint-paths.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Markdown Linting using rumdl"

# The toolchain not being installed is a distinct failure from the linter
# finding something, and the messages say which. See tools/lint-yaml.sh.
if [[ "$(command -v uv)" = "" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: uv is required, see (https://docs.astral.sh/uv/) or run: brew install uv";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

if ! uv run --frozen --group lint rumdl --version >/dev/null 2>&1; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: rumdl is not available. Run \"make install\".";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# One invocation over the files git tracks, not one per directory.
#
# The previous shape ran markdownlint once per directory glob and kept only the
# first non-zero status, so its "Summary: N error(s)" line reported the last
# group's count. It printed "Summary: 2 error(s)" over 3718 findings.
#
# rumdl replaced markdownlint-cli2 and reads the same .markdownlint.yaml, so
# the rule set did not move with the engine. The one rule rumdl adds, MD076,
# is disabled in that file.
#
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
      | xargs -0 uv run --frozen --group lint rumdl check --config "$(pwd)/.markdownlint.yaml"; then
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
