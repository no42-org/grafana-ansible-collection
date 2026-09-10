#!/usr/bin/env bash
#
# Lint the release machinery.
#
# Scope: the release machinery this repository owns.
#
#   - tools/*.sh                     the build, rename and lint scripts
#   - .github/workflows/             every workflow's hygiene
#   - galaxy.yml, dependabot.yml     parseable, and with the fields the
#                                    release needs
#
# It is not the full `make ci-lint` set, and that is a division of labour
# rather than a gap. The full set gates a release too, in the `lint` job of
# .github/workflows/gate.yml, which both ci.yml and release.yml call. This
# script is the release *machinery* check, and its value is that it needs no
# pipenv and no node_modules, so it runs in seconds locally.
#
# Two earlier justifications for the narrow scope were wrong and are recorded
# here so they are not reinstated. "ci-lint is red on a pristine tree and
# fixing it would break the upstream-merge property": the findings were real
# but cost four newly-diverging files of whitespace, and they are fixed. "The
# pipenv toolchain is too fragile for the release path": `make install` has
# succeeded on every CI run, because setup-python supplies the Python 3.10 that
# Pipfile pins. The fragility is local, not in CI.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

heading "Grafana Ansible Collection" "Linting the release machinery"

# make sure shellcheck exists
if [[ "$(command -v shellcheck)" = "" ]]; then
  echo >&2 "shellcheck command is required, see (https://www.shellcheck.net/) or run: brew install shellcheck";
  exit 1;
fi

# yamllint on PATH if the environment provides one, otherwise the pinned copy
# in the project's uv environment. Preferring PATH keeps this script usable
# before `make install` has run, which matters because it is the one lint gate
# that needs no toolchain provisioning.
yamllintCmd=()
if [[ "$(command -v yamllint)" != "" ]]; then
  yamllintCmd=(yamllint)
elif uv run --frozen --group lint yamllint --version >/dev/null 2>&1; then
  yamllintCmd=(uv run --frozen --group lint yamllint)
else
  echo >&2 "TOOLCHAIN NOT INSTALLED: yamllint is required, see (https://pypi.org/project/yamllint/). Run \"make install\".";
  exit 1;
fi

statusCode=0

echo "  ‣ shellcheck tools/*.sh"
if ! shellcheck -x tools/*.sh; then
  lintError "shellcheck reported issues in tools/"
  statusCode=1
fi

# Not --strict here, unlike release.yml below. Three inherited workflows carry
# `run:` lines over 150 characters, which .yamllint classes as a warning;
# --strict would promote those to errors and make the gate demand that
# inherited files be reflowed, which this fork does not do. Errors still fail.
# The regression guard for honest-ci-gates.
#
# tools/lint-yaml.sh and tools/lint-ansible.sh both ended on
#
#   if [[ "$sourced" == "1" ]]; then
#     return "$statusCode"
#   fi
#
# `make ci-lint-*` executes these scripts rather than sourcing them, so
# sourced=0, the closing `if` evaluates false, and in bash a false `if` with no
# `else` yields exit status 0. Both scripts reported success while their linter
# printed errors: CI run 34446534704 showed 61 error annotations on a step
# whose conclusion was `success`.
#
# Explicit rather than delegated to shellcheck, which has no check for this.
# The pattern is valid bash that does exactly what it says; the defect is that
# what it says is not what the caller needs. No linter can know that, so the
# assertion has to be written down.
echo "  ‣ every tools/lint-*.sh propagates its exit status"
for lintScript in tools/lint-*.sh; do
  if ! grep -qE '^[[:space:]]*exit[[:space:]]+"\$\{?statusCode\}?"' "${lintScript}"; then
    lintError "${lintScript} captures statusCode but never exits with it: add 'else exit \"\$statusCode\"'"
    statusCode=1
  fi
done

echo "  ‣ yamllint .github/workflows/"
if ! "${yamllintCmd[@]}" --config-file "$(pwd)/.yamllint" .github/workflows/; then
  lintError "yamllint reported errors in .github/workflows/"
  statusCode=1
fi

echo "  ‣ yamllint --strict .github/workflows/release.yml"
if ! "${yamllintCmd[@]}" --strict --config-file "$(pwd)/.yamllint" .github/workflows/release.yml; then
  lintError "yamllint reported issues in .github/workflows/release.yml"
  statusCode=1
fi

# actionlint catches what yamllint cannot: bad expressions, unknown contexts,
# broken needs graphs, and retired runner labels -- which is how the
# `ubuntu-20.04` jobs that sat queued forever would have been caught.
#
# Required, not optional. It used to run only if it happened to be installed,
# which the actions-hygiene proposal correctly called "not enforcement".
if [[ "$(command -v actionlint)" = "" ]]; then
  echo >&2 "actionlint command is required, see (https://github.com/rhysd/actionlint) or run: brew install actionlint";
  exit 1;
fi
echo "  ‣ actionlint .github/workflows/"
if ! actionlint; then
  lintError "actionlint reported issues in .github/workflows/"
  statusCode=1
fi

# The two pin checks, mechanically. Every third-party `uses:` must be a
# 40-character commit SHA -- a tag is mutable and can be moved to point at
# different code -- and must carry the full semantic version in a trailing
# comment, so a reviewer can cross-reference upstream release notes and
# Dependabot's rewrites match the format. Local reusable workflows (`./...`)
# resolve to the current commit and are exempt.
# zizmor checks what actionlint does not: template injection, credential
# persistence, over-broad permissions, dangerous triggers.
#
# --min-severity low, deliberately. The three informational findings on a clean
# tree are two template-injection hits on
# `needs.verify-version.outputs.version` -- a value read from galaxy.yml and
# already checked against the tag by the verify-version job, so it is not
# attacker-controllable -- and a suggestion to replace the release action with
# `gh release`. Failing the gate on those would make it noise. Anything at low
# or above fails.
if [[ "$(command -v zizmor)" = "" ]]; then
  echo >&2 "zizmor command is required, see (https://docs.zizmor.sh/) or run: pip install zizmor";
  exit 1;
fi
echo "  ‣ zizmor .github/workflows/"
if ! zizmor --no-progress --min-severity low .github/workflows/; then
  lintError "zizmor reported issues in .github/workflows/"
  statusCode=1
fi

echo "  ‣ every action pinned to a SHA with a full-semver comment"
unpinnedRefs="$(grep -rn 'uses:' .github/workflows/ \
  | grep -v 'uses: \./' \
  | grep -vE '@(sha256:)?[0-9a-f]{40}' || true)"
if [[ -n "${unpinnedRefs}" ]]; then
  echo "${unpinnedRefs}"
  lintError "unpinned action reference(s): pin to a 40-character commit SHA"
  statusCode=1
fi

missingVersionComments="$(grep -rnE '@(sha256:)?[0-9a-f]{40}' .github/workflows/ \
  | grep -vE '#[[:space:]]*v[0-9]+\.[0-9]+\.[0-9]+' || true)"
if [[ -n "${missingVersionComments}" ]]; then
  echo "${missingVersionComments}"
  lintError "pinned action(s) without a full-semver comment: use '# vX.Y.Z', not '# v4'"
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
