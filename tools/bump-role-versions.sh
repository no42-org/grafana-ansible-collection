#!/usr/bin/env bash
#
# Open one pull request per role whose pin is behind upstream.
#
# Reads the JSON report tools/check-role-versions.py writes, and for each entry
# branches from main, rewrites the single version line, and raises a pull
# request. It never merges anything: the bump has to pass that role's tests on
# both package families first, and a human decides.
#
# That verification is the whole reason pinning is safe rather than a risk moved
# elsewhere. An unverified bump is how the tempo role came to ship a
# configuration Tempo rejects.
#
# Lives here rather than inline in the workflow so shellcheck actually lints it
# -- the first attempt put this in a `run:` block, where actionlint's shellcheck
# read the markdown backticks in the pull request body as shell substitutions.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "./tools/includes/logging.sh"

heading "Grafana Ansible Collection" "Proposing role version bumps"

report="${ROLE_VERSION_REPORT:-}"
if [[ -z "${report}" || ! -f "${report}" ]]; then
  echo >&2 "ROLE_VERSION_REPORT must point at the JSON written by check-role-versions.py"
  exit 1
fi

count="$(python3 -c 'import json,os,sys; print(len(json.load(open(os.environ["ROLE_VERSION_REPORT"]))))')"
info "roles behind upstream: ${count}"
if [[ "${count}" -eq 0 ]]; then
  success "every tracked pin is current; nothing to open"
  exit 0
fi

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

plan="$(mktemp)"
python3 -c '
import json, os
for e in json.load(open(os.environ["ROLE_VERSION_REPORT"])):
    print("\t".join([e["role"], e["defaults"], e["variable"],
                     e["current"], e["upstream"], e["repo"]]))
' > "${plan}"

while IFS=$'\t' read -r role defaults variable current upstream repo; do
  branch="chore/bump-${role}-${upstream}"

  if git ls-remote --exit-code --heads origin "${branch}" >/dev/null 2>&1; then
    info "${role}: ${branch} already exists, skipping"
    continue
  fi

  git checkout -B "${branch}" origin/main >/dev/null 2>&1
  python3 - "${defaults}" "${variable}" "${current}" "${upstream}" <<'PYEOF'
import re, sys
path, var, cur, new = sys.argv[1:5]
text = open(path).read()
bumped = re.sub(rf'^({re.escape(var)}: *"?){re.escape(cur)}("?)$',
                rf'\g<1>{new}\g<2>', text, count=1, flags=re.M)
assert bumped != text, f"{path}: {var} {cur} was not replaced"
open(path, "w").write(bumped)
PYEOF

  git add "${defaults}"
  git commit -s \
    -m "chore(${role}): bump to ${upstream}" \
    -m "${repo} released ${upstream}; this role pinned ${current}." \
    -m "Opened by .github/workflows/role-versions.yml. Not to be merged until the role tests pass on both package families: verifying the bump is what makes pinning safe rather than a risk moved elsewhere." \
    -m "Assisted-by: GitHubActions:role-versions"
  git push -u origin "${branch}" >/dev/null 2>&1

  # Built with a heredoc rather than printf: the body is markdown, its
  # backticks are code spans rather than command substitution, and a quoted
  # heredoc keeps the shell out of it entirely.
  body="$(cat <<EOF
${repo} released \`${upstream}\`; this role pinned \`${current}\`.

Opened automatically by \`.github/workflows/role-versions.yml\`.

**Do not merge until \`${role}\` passes on both package families.** Verifying the
bump is the reason pinning is safe rather than a risk moved elsewhere.
EOF
)"
  gh pr create --base main --head "${branch}" \
    --title "chore(${role}): bump to ${upstream}" \
    --body "${body}" \
    --label dependencies
  success "${role}: opened a pull request for ${current} -> ${upstream}"
done < "${plan}"

rm -f "${plan}"
