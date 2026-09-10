#!/usr/bin/env bash
#
# Report the upstream contributions this fork carries ahead of upstream.
#
# This fork is a curated downstream: it cherry-picks open upstream pull requests
# and drops each one once upstream merges it. The carried set is not maintained
# as prose, because prose that must be updated by hand is prose that will be
# wrong. It is derived from git history instead: every carried commit records
# its origin via `git cherry-pick -x`, so the set is discoverable with
#
#   git log --grep "cherry picked from commit"
#
# For each carried commit this script resolves the upstream commit to its pull
# request and reports that pull request's current state. Anything upstream has
# merged is redundant here and can be dropped at the next `git merge
# upstream/main`.
#
# Usage: tools/carried-prs.sh [--release-notes] [<base>]
#
#   --release-notes  emit a markdown list for GitHub release notes instead of
#                    the table. Resolves pull request numbers locally and does
#                    not query pull request state, so it needs no credentials.
#   <base>           commit to enumerate from, defaulting to the merge base
#                    with upstream/main, which is the point this fork diverged.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

readonly UPSTREAM_REPO="grafana/grafana-ansible-collection"
readonly UPSTREAM_REMOTE="upstream"

release_notes=0
if [[ "${1:-}" == "--release-notes" ]]; then
  release_notes=1
  shift
fi

if [[ "${release_notes}" -eq 0 ]]; then
  heading "Grafana Ansible Collection" "Upstream contributions carried by this fork"
fi

# gh is only needed to report pull request state, which release-notes mode skips.
if [[ "${release_notes}" -eq 0 ]] && [[ "$(command -v gh)" = "" ]]; then
  echo >&2 "gh command is required, see (https://cli.github.com/) or run: brew install gh";
  exit 1;
fi

if ! git remote get-url "${UPSTREAM_REMOTE}" >/dev/null 2>&1; then
  emergency "no '${UPSTREAM_REMOTE}' remote; add it with: git remote add ${UPSTREAM_REMOTE} https://github.com/${UPSTREAM_REPO}.git"
fi

base="${1:-}"
if [[ -z "${base}" ]]; then
  base="$(git merge-base HEAD "${UPSTREAM_REMOTE}/main" 2>/dev/null || true)"
fi
if [[ -z "${base}" ]]; then
  emergency "could not determine a base; pass one explicitly or fetch ${UPSTREAM_REMOTE}"
fi

if [[ "${release_notes}" -eq 0 ]]; then
  info "enumerating carried commits since $(git rev-parse --short "${base}")"
fi

# Pull request head refs, used to map a carried origin commit back to its pull
# request. Fetched on demand: without them nothing can be resolved.
pr_refs="$(git for-each-ref --format='%(refname:short)' "refs/remotes/${UPSTREAM_REMOTE}/pr/*")"
if [[ -z "${pr_refs}" ]]; then
  [[ "${release_notes}" -eq 0 ]] && info "fetching upstream pull request refs (first run)"
  git fetch -q "${UPSTREAM_REMOTE}" "refs/pull/*/head:refs/remotes/${UPSTREAM_REMOTE}/pr/*" || true
  pr_refs="$(git for-each-ref --format='%(refname:short)' "refs/remotes/${UPSTREAM_REMOTE}/pr/*")"
fi

# Collect the carried commits and the upstream SHA each came from.
carried=()
while IFS= read -r line; do
  [[ -n "${line}" ]] && carried+=("${line}")
done < <(
  git log --reverse --format='%H' --grep='cherry picked from commit' "${base}..HEAD" \
    | while IFS= read -r sha; do
        origin="$(git log -1 --format='%B' "${sha}" \
          | sed -n 's/.*cherry picked from commit \([0-9a-f]\{7,40\}\).*/\1/p' | head -1)"
        [[ -n "${origin}" ]] && echo "${sha} ${origin}"
      done
)

if [[ "${#carried[@]}" -eq 0 ]]; then
  if [[ "${release_notes}" -eq 1 ]]; then
    echo "_No upstream contributions are carried ahead of upstream in this release._"
  else
    success "no carried contributions; this fork matches its upstream base"
  fi
  exit 0
fi

if [[ "${release_notes}" -eq 0 ]]; then
  printf "\n  %-9s %-9s %-8s %-22s %s\n" "LOCAL" "UPSTREAM" "PR" "AUTHOR" "STATE"
  printf "  %s\n" "------------------------------------------------------------------------------"
fi

droppable=0
unknown=0

for entry in "${carried[@]}"; do
  local_sha="${entry%% *}"
  origin_sha="${entry##* }"
  author="$(git log -1 --format='%an' "${local_sha}")"

  # Resolve the upstream commit to a pull request by ancestry against the
  # fetched refs/pull/*/head refs. The commits API cannot do this: a pull
  # request's head commits live in the contributor's fork, so
  # repos/<upstream>/commits/<sha>/pulls returns nothing for them.
  number=""
  for ref in ${pr_refs}; do
    if git merge-base --is-ancestor "${origin_sha}" "${ref}" 2>/dev/null; then
      number="${ref##*/}"
      break
    fi
  done

  if [[ -z "${number}" ]]; then
    if [[ "${release_notes}" -eq 1 ]]; then
      printf -- "- %s by %s (upstream commit \`%s\`)\n" \
        "$(git log -1 --format='%s' "${local_sha}")" "${author}" "${origin_sha:0:12}"
    else
      printf "  %-9s %-9s %-8s %-22s %s\n" \
        "${local_sha:0:8}" "${origin_sha:0:8}" "-" "${author:0:22}" "no pull request found"
    fi
    unknown=$(( unknown + 1 ))
    continue
  fi

  if [[ "${release_notes}" -eq 1 ]]; then
    printf -- "- %s by %s in https://github.com/%s/pull/%s\n" \
      "$(git log -1 --format='%s' "${local_sha}")" "${author}" "${UPSTREAM_REPO}" "${number}"
    continue
  fi

  pr_json="$(gh pr view "${number}" --repo "${UPSTREAM_REPO}" \
    --json state,mergedAt,isDraft 2>/dev/null || true)"
  if [[ -z "${pr_json}" ]]; then
    state="unknown"; merged="False"
  else
    state="$(echo "${pr_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["state"].lower())')"
    merged="$(echo "${pr_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["mergedAt"] is not None)')"
  fi

  if [[ "${merged}" == "True" ]]; then
    printf "  %-9s %-9s %-8s %-22s %s\n" \
      "${local_sha:0:8}" "${origin_sha:0:8}" "#${number}" "${author:0:22}" "MERGED upstream, droppable"
    droppable=$(( droppable + 1 ))
  else
    printf "  %-9s %-9s %-8s %-22s %s\n" \
      "${local_sha:0:8}" "${origin_sha:0:8}" "#${number}" "${author:0:22}" "${state}, still carried"
  fi
done

if [[ "${release_notes}" -eq 1 ]]; then
  exit 0
fi

echo ""
info "carried: ${#carried[@]}"
[[ "${unknown}" -gt 0 ]] && warning "unresolved: ${unknown} (no pull request found for the recorded origin)"

if [[ "${droppable}" -gt 0 ]]; then
  warning "droppable: ${droppable} contribution(s) merged upstream"
  warning "after the next 'git merge ${UPSTREAM_REMOTE}/main', revert or drop those commits"
  exit 0
fi

success "all ${#carried[@]} carried contribution(s) are still open upstream"
