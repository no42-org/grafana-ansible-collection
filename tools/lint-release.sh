#!/usr/bin/env bash
#
# Lint the release machinery.
#
# `make ci-lint` cannot gate a release while it is red on a pristine tree from
# inherited findings, so this gate is scoped to the files that build and check
# the collection:
#
#   - tools/*.sh                          the build and lint scripts
#
# galaxy.yml and .github/dependabot.yml carry inherited style debt (truthy,
# line-length, indentation), so they are checked for being parseable YAML
# rather than for style.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

heading "Grafana Ansible Collection" "Linting the release machinery"

# make sure shellcheck exists
if [[ "$(command -v shellcheck)" = "" ]]; then
  echo >&2 "shellcheck command is required, see (https://www.shellcheck.net/) or run: brew install shellcheck";
  exit 1;
fi

statusCode=0

echo "  ‣ shellcheck tools/*.sh"
if ! shellcheck -x tools/*.sh; then
  lintError "shellcheck reported issues in tools/"
  statusCode=1
fi

echo "  ‣ yaml parse galaxy.yml .github/dependabot.yml"
if ! python3 -c "
import sys, yaml
for path in ('galaxy.yml', '.github/dependabot.yml'):
    with open(path) as handle:
        yaml.safe_load(handle)
    print('    %s parses' % path)
"; then
  lintError "galaxy.yml or .github/dependabot.yml is not valid YAML"
  statusCode=1
fi

# galaxy.yml drives the whole release: a wrong namespace publishes nowhere, and a
# version that disagrees with the tag is caught in CI but is cheaper to catch here.
echo "  ‣ galaxy.yml required fields"
if ! python3 -c "
import sys, yaml
meta = yaml.safe_load(open('galaxy.yml'))
missing = [key for key in ('namespace', 'name', 'version', 'build_ignore') if key not in meta]
if missing:
    sys.exit('    galaxy.yml is missing: %s' % ', '.join(missing))
print('    namespace=%s name=%s version=%s' % (meta['namespace'], meta['name'], meta['version']))
"; then
  lintError "galaxy.yml is missing required fields"
  statusCode=1
fi

if [[ "${statusCode}" == "0" ]]; then
  success "no issues found"
fi

exit "${statusCode}"
