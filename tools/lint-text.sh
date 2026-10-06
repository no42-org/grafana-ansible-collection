#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

source "./tools/includes/lint-paths.sh"

# output the heading
heading "Grafana Ansible Collections" "Performing Text Linting using codespell"

# The toolchain not being installed is a distinct failure from the linter
# finding something, and the messages say which. See tools/lint-yaml.sh.
if [[ "$(command -v uv)" = "" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: uv is required, see (https://docs.astral.sh/uv/) or run: brew install uv";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

if ! uv run --frozen --group lint codespell --version >/dev/null 2>&1; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: codespell is not available. Run \"make install\".";
  echo >&2 "This is not a lint failure. No file has been checked.";
  exit 1;
fi

# determine whether or not the script is called directly or sourced
(return 0 2>/dev/null) && sourced=1 || sourced=0

# codespell replaced textlint. Its built-in dictionary (`-D -`) is the
# misspelling rule; tools/codespell-dictionary.txt carries the Grafana rewrites
# that .textlintrc used to, in codespell's `wrong->right` form, which admits no
# comments, so the reasoning is here:
#
#   examplars    -> exemplars
#   grafanalabs  -> Grafana Labs
#   grafanacloud -> Grafana Cloud
#
# `datasource -> data source` is deliberately not carried. codespell reads raw
# text and cannot tell a fenced command from a sentence, and `datasource` is
# the name of a module this repository documents by name. The casing terms
# (Grafana, Prometheus, GitHub, ...) moved to MD044 in .markdownlint.yaml,
# because codespell matches case-insensitively and cannot enforce one. The rest
# of .textlintrc was textlint's default JavaScript-ecosystem list, pasted in
# verbatim, and was dropped rather than ported.
#
# One invocation over the prose this fork authors, scoped exactly as
# tools/lint-markdown.sh is and for the same reason: the top-level README, the
# role READMEs and examples/ are upstream's documents, and this fork does not
# reformat inherited files. See the comment there.
statusCode=0
if ! git ls-files -z -- '*.md' \
        ':!:README.md' ':!:roles/*/README.md' ':!:examples/*.md' ':!:CLAUDE.md' \
      | xargs -0 uv run --frozen --group lint codespell -D - -D "$(pwd)/tools/codespell-dictionary.txt"; then
  statusCode=1
fi

if [[ "$statusCode" == "0" ]]; then
  echo "no issues found"
fi

echo ""
echo ""

# if the script was called by another, send a valid exit code
if [[ "$sourced" == "1" ]]; then
  return "$statusCode"
else
  exit "$statusCode"
fi
