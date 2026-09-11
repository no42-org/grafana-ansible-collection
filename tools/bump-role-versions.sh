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

# The bot identity for the commits below, as environment variables rather than
# `git config`. `git config` writes .git/config, which in CI is a throwaway
# checkout but locally is the maintainer's own clone -- and epic 3 of this
# change required running this script locally to prove it opens a real pull
# request. It did, and it also left every subsequent commit in that clone
# signed off by github-actions[bot]. These variables last exactly as long as
# this process.
export GIT_AUTHOR_NAME="github-actions[bot]"
export GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com"
export GIT_COMMITTER_NAME="${GIT_AUTHOR_NAME}"
export GIT_COMMITTER_EMAIL="${GIT_AUTHOR_EMAIL}"

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

  git checkout -B "${branch}" origin/main
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
  # -s would take the trailer from user.name/user.email, which is deliberately
  # not set here, so the sign-off is spelled out instead.
  git commit \
    -m "chore(${role}): bump to ${upstream}" \
    -m "${repo} released ${upstream}; this role pinned ${current}." \
    -m "Opened by .github/workflows/role-versions.yml. Not to be merged until the role tests pass on both package families: verifying the bump is what makes pinning safe rather than a risk moved elsewhere." \
    -m "Assisted-by: GitHubActions:role-versions
Signed-off-by: ${GIT_AUTHOR_NAME} <${GIT_AUTHOR_EMAIL}>"
  # Not silenced. Hiding a push failure here is how the first run of this
  # script produced a confusing "No commits between main and ..." from
  # `gh pr create`: the push had failed and nothing said so.
  if ! git push -u origin "${branch}"; then
    echo >&2 "${role}: could not push ${branch}"
    exit 1
  fi

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
  # Retried, because a freshly pushed ref is not always visible to the API
  # yet. The first real run of this script failed here with "No commits
  # between main and chore/... Head ref must be a branch" -- the push had
  # succeeded and GitHub simply had not caught up. Retrying the same command
  # a few seconds later worked.
  opened=0
  for attempt in 1 2 3 4 5; do
    if gh pr create --base main --head "${branch}" \
          --title "chore(${role}): bump to ${upstream}" \
          --body "${body}" \
          --label dependencies; then
      opened=1
      break
    fi
    warning "${role}: pull request creation attempt ${attempt} failed, retrying"
    sleep 5
  done
  if [[ "${opened}" -ne 1 ]]; then
    echo >&2 "${role}: could not open a pull request for ${branch}"
    exit 1
  fi
  success "${role}: opened a pull request for ${current} -> ${upstream}"
done < "${plan}"

rm -f "${plan}"
