#!/usr/bin/env bash
#
# Track the upstream issues and pull requests this fork may want to act on.
#
# This is not tools/carried-prs.sh and the two answer opposite questions. That
# script derives what the fork *already carries* from git history: it reads
# `cherry picked from commit` trailers and reports whether upstream has since
# merged them. This one records what upstream *has open* -- the candidate set,
# none of which is in this tree yet -- so a release can be planned against it
# instead of against whatever happened to be noticed that week.
#
# The candidate set lives in a GitHub Project rather than in a file, because a
# file would have to be regenerated to stay true and would conflict on every
# upstream merge. The board is seeded with draft items: no issue is opened in
# this repository, so triage costs the fork's own tracker nothing.
#
# Field ownership is the reason a re-run is safe. The sync writes only the
# fields it derives from upstream:
#
#   Upstream        number   the match key; never rewritten after creation
#   Kind            select   Issue or PR
#   Upstream state  select   open, merged or closed
#   Last synced     date     when this script last confirmed the row
#
# and never touches the four that are a maintainer's judgement:
#
#   Fork decision   select   seeded to Untriaged on creation, then yours
#   Epic            select   which subsystem the work belongs to
#   Change type     select   Bug, Enhancement or Maintenance
#   Target release  text     yours
#
# Epic is by subsystem rather than by theme, and the field is single-select, so
# an item sits in exactly one. The rule that keeps that decidable: work in a
# module under plugins/ is grafana-api-modules, work in a role's tasks is that
# role's epic. Upstream's own labels cannot supply any of this -- 54 of its 57
# open issues carry no label at all.
#
# Usage: tools/upstream-tracker.sh [--bootstrap | --report | --check-token]
#
#   --bootstrap    create the project and any missing field, then exit. Idempotent,
#                  so the board is reproducible from this repository rather than
#                  assembled by hand in a browser.
#   --report       print the board as a table and exit. Queries no upstream state.
#   --check-token  confirm the token can still write the board, and exit. Writes
#                  nothing. This is the scheduled job's pre-flight.
#   (no flag)      sync: add upstream items the board is missing, refresh the
#                  derived fields on the ones it already has.
#
# Environment:
#   UPSTREAM_TRACKER_OWNER  project owner, defaults to no42-org
#   UPSTREAM_TRACKER_TITLE  project title, defaults to "Upstream tracking"
#
# Needs a token with the `project` scope. GITHUB_TOKEN in Actions does not have
# it and cannot be granted it; see .github/workflows/upstream-tracker.yml.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

readonly UPSTREAM_REPO="grafana/grafana-ansible-collection"
readonly PROJECT_OWNER="${UPSTREAM_TRACKER_OWNER:-no42-org}"
readonly PROJECT_TITLE="${UPSTREAM_TRACKER_TITLE:-Upstream tracking}"

# Field definitions, in board order: name|datatype|comma-separated options.
# --bootstrap creates whatever is missing, so adding a row here and re-running
# is how the board gains a field.
readonly FIELD_SPECS=(
  "Upstream|NUMBER|"
  "Kind|SINGLE_SELECT|Issue,PR"
  "Upstream state|SINGLE_SELECT|open,merged,closed"
  "Fork decision|SINGLE_SELECT|Untriaged,Carry,Fix here,Not applicable,Superseded,Done"
  "Epic|SINGLE_SELECT|grafana-dashboards,grafana-install,grafana-api-modules,alloy,mimir,tempo,otel-collector,cross-role,new-roles"
  # "Type" is refused: GitHub reserves the name for its own issue-type
  # feature, so the field has to be called something else.
  "Change type|SINGLE_SELECT|Bug,Enhancement,Maintenance"
  "Target release|TEXT|"
  "Last synced|DATE|"
)

mode="sync"
case "${1:-}" in
  --bootstrap)   mode="bootstrap" ;;
  --report)      mode="report" ;;
  --check-token) mode="check-token" ;;
  "")            ;;
  *)             emergency "unknown argument '${1}'; see the usage comment in $0" ;;
esac

if [[ "${mode}" != "report" ]]; then
  heading "Grafana Ansible Collection" "Upstream issues and pull requests to triage"
fi

if [[ "$(command -v gh)" = "" ]]; then
  emergency "gh command is required, see (https://cli.github.com/) or run: brew install gh"
fi

# ---------------------------------------------------------------------------
# Project and field resolution
# ---------------------------------------------------------------------------

# Resolve the project by title. Titles are not unique to GitHub, but they are
# the only handle a checked-in script can carry: a project number is assigned at
# creation and would have to be pasted in here after the fact.
#
# Three outcomes, and conflating any two of them creates a second board that
# silently competes with the first. A failed lookup -- a revoked token, a
# transient error, a board someone closed, since `gh project list` hides closed
# projects -- must not read as "no project exists", or --bootstrap creates a
# duplicate and every later sync picks whichever one sorts first, seeding 88
# fresh drafts onto the empty one while the triaged board is never read again.
# Two matches are equally unrecoverable and are refused rather than guessed at.
project_number() {
  local listed
  if ! listed="$(gh project list --owner "${PROJECT_OWNER}" --limit 100 --closed \
    --format json --jq ".projects[] | select(.title == \"${PROJECT_TITLE}\") | .number")"; then
    emergency "could not list projects for ${PROJECT_OWNER}; the token is expired or lost its Projects permission"
  fi
  if [[ "$(wc -l <<< "${listed}" | tr -d ' ')" -gt 1 ]]; then
    emergency "more than one project titled '${PROJECT_TITLE}' under ${PROJECT_OWNER}: $(tr '\n' ' ' <<< "${listed}")"
  fi
  echo "${listed}"
}

number="$(project_number)"

# A pre-flight that answers the question the scheduled job actually depends on:
# can this token still write this board. Checking that the secret merely exists
# catches only the day it is first set up; the failure that happens later is an
# expiry, and a weekly job that fails with a raw authentication error once a
# week is one nobody reads.
#
# viewerCanUpdate is GitHub's own answer, so the write permission is tested
# without writing anything. A token downgraded to read-only fails here rather
# than halfway through a sync, having already rewritten part of the board.
if [[ "${mode}" == "check-token" ]]; then
  [[ -z "${number}" ]] && \
    emergency "no project titled '${PROJECT_TITLE}' under ${PROJECT_OWNER}; run: make upstream-bootstrap"

  # $org and $num are GraphQL variables, bound by the -f and -F flags below.
  # The shell must not expand them, so the query stays single-quoted.
  # shellcheck disable=SC2016
  if ! can_update="$(gh api graphql \
    -f query='query($org:String!,$num:Int!){organization(login:$org){projectV2(number:$num){viewerCanUpdate}}}' \
    -f org="${PROJECT_OWNER}" -F num="${number}" \
    --jq '.data.organization.projectV2.viewerCanUpdate' 2>&1)"; then
    emergency "PROJECTS_TOKEN is expired or lost its Projects permission: ${can_update}"
  fi

  if [[ "${can_update}" != "true" ]]; then
    emergency "PROJECTS_TOKEN can read project #${number} but not write it; it needs organization 'Projects: read and write', not read"
  fi

  success "PROJECTS_TOKEN can read and write project #${number} '${PROJECT_TITLE}'"
  exit 0
fi

if [[ "${mode}" == "bootstrap" ]]; then
  if [[ -z "${number}" ]]; then
    info "creating project '${PROJECT_TITLE}' under ${PROJECT_OWNER}"
    gh project create --owner "${PROJECT_OWNER}" --title "${PROJECT_TITLE}" --format json >/dev/null
    number="$(project_number)"
    [[ -z "${number}" ]] && emergency "created the project but could not resolve its number"
    success "created project #${number}"
  else
    info "project '${PROJECT_TITLE}' already exists as #${number}"
  fi

  existing_fields="$(gh project field-list "${number}" --owner "${PROJECT_OWNER}" \
    --limit 100 --format json --jq '.fields[].name')"

  created=0
  for spec in "${FIELD_SPECS[@]}"; do
    IFS='|' read -r fname ftype foptions <<< "${spec}"
    if grep -qxF "${fname}" <<< "${existing_fields}"; then
      continue
    fi
    if [[ -n "${foptions}" ]]; then
      gh project field-create "${number}" --owner "${PROJECT_OWNER}" \
        --name "${fname}" --data-type "${ftype}" \
        --single-select-options "${foptions}" >/dev/null
    else
      gh project field-create "${number}" --owner "${PROJECT_OWNER}" \
        --name "${fname}" --data-type "${ftype}" >/dev/null
    fi
    info "created field '${fname}' (${ftype})"
    created=$(( created + 1 ))
  done

  if [[ "${created}" -eq 0 ]]; then
    success "all ${#FIELD_SPECS[@]} fields already present; nothing to do"
  else
    success "created ${created} field(s)"
  fi
  info "next: make upstream-sync"
  exit 0
fi

if [[ -z "${number}" ]]; then
  emergency "no project titled '${PROJECT_TITLE}' under ${PROJECT_OWNER}; run: make upstream-bootstrap"
fi

fields_json="$(gh project field-list "${number}" --owner "${PROJECT_OWNER}" \
  --limit 100 --format json)"

# field_id <name> -- the project field id, or empty if the board lacks the field.
field_id() {
  python3 -c '
import json, sys
fields = json.loads(sys.argv[1])["fields"]
print(next((f["id"] for f in fields if f["name"] == sys.argv[2]), ""))
' "${fields_json}" "${1}"
}

# option_id <field name> <option name> -- a single-select option id.
#
# Fails rather than returning empty. --bootstrap creates missing fields but
# never reconciles the options on a field that already exists, so adding an
# option to FIELD_SPECS, or renaming one in the browser, leaves the board and
# this script disagreeing. Passing the empty string on to `gh project item-edit
# --single-select-option-id` fails mid-loop with an opaque API error and a
# half-updated board; this names the cause instead.
option_id() {
  local id
  id="$(python3 -c '
import json, sys
fields = json.loads(sys.argv[1])["fields"]
field = next((f for f in fields if f["name"] == sys.argv[2]), None)
opts = (field or {}).get("options", [])
print(next((o["id"] for o in opts if o["name"] == sys.argv[3]), ""))
' "${fields_json}" "${1}" "${2}")"
  [[ -z "${id}" ]] && emergency "field '${1}' on project #${number} has no option '${2}'; the board and FIELD_SPECS disagree"
  echo "${id}"
}

for spec in "${FIELD_SPECS[@]}"; do
  IFS='|' read -r fname _ _ <<< "${spec}"
  [[ -z "$(field_id "${fname}")" ]] && \
    emergency "project #${number} has no '${fname}' field; run: make upstream-bootstrap"
done

project_id="$(gh project view "${number}" --owner "${PROJECT_OWNER}" --format json --jq '.id')"

FIELD_UPSTREAM="$(field_id "Upstream")"
FIELD_KIND="$(field_id "Kind")"
FIELD_STATE="$(field_id "Upstream state")"
FIELD_DECISION="$(field_id "Fork decision")"
FIELD_SYNCED="$(field_id "Last synced")"

# ---------------------------------------------------------------------------
# Board contents
# ---------------------------------------------------------------------------

# The board, as one "<upstream number> <item id> <kind> <state> <decision> <target> <epic> <change type> <repair>"
# line per item.
#
# BOARD_LIMIT is checked, not trusted. The board only grows -- closed upstream
# items stay on it by design -- and a silently truncated listing would fail
# every on_board test, recreating the truncated items as duplicates on every
# run thereafter.
readonly BOARD_LIMIT=1000
board_json="$(gh project item-list "${number}" --owner "${PROJECT_OWNER}" \
  --limit "${BOARD_LIMIT}" --format json)"

board_total="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["totalCount"])' "${board_json}")"
if [[ "${board_total}" -gt "${BOARD_LIMIT}" ]]; then
  emergency "board has ${board_total} items but only ${BOARD_LIMIT} were listed; raise BOARD_LIMIT"
fi

board="$(python3 -c '
import json, re, sys

def flat(value):
    return str(value).replace(" ", "_") or "-"

# Creating an item is not one operation: the draft is created, then Upstream is
# written. A run killed between the two -- the job timing out mid-seed, a
# transient 5xx under set -e -- leaves a draft with no Upstream number. Matching
# on the number alone would not recognise it, so the next run would create a
# second draft for the same upstream item, and so would every run after that.
# The title this script writes is the fallback key, and such a row is flagged
# for repair so the sync can put the missing number back.
TITLE = re.compile(r"^\[(Issue|PR) #(\d+)\] ")

rows = {}
for item in json.loads(sys.argv[1])["items"]:
    upstream, repair = item.get("upstream"), "ok"
    if upstream is None:
        # No number and no title this script would have written: a row somebody
        # added by hand. Left strictly alone.
        match = TITLE.match(item.get("title", ""))
        if not match:
            continue
        upstream, repair = match.group(2), "repair"
    upstream = int(upstream)
    # One row per upstream number, preferring the one that already carries the
    # number. A board that a previous version duplicated still syncs correctly
    # rather than emitting two item ids for one number, which would make every
    # later lookup return two lines and corrupt the field writes.
    if upstream in rows and rows[upstream][-1] == "ok":
        continue
    # gh keys custom fields by the field name lowercased, spaces and all.
    rows[upstream] = (item["id"],
                      flat(item.get("kind", "-")),
                      flat(item.get("upstream state", "-")),
                      flat(item.get("fork decision", "-")),
                      flat(item.get("target release", "-")),
                      flat(item.get("epic", "-")),
                      flat(item.get("change type", "-")),
                      repair)

for upstream in sorted(rows):
    print(upstream, *rows[upstream])
' "${board_json}")"

on_board() {
  grep -qE "^${1} " <<< "${board}"
}

board_field() {
  awk -v n="${1}" -v col="${2}" '$1 == n { print $col }' <<< "${board}"
}

if [[ "${mode}" == "report" ]]; then
  if [[ -z "${board}" ]]; then
    echo "The board is empty. Run: make upstream-sync"
    exit 0
  fi
  # "STATE", not "UPSTREAM": the upstream number is the # column, and a field
  # named Upstream over a column of "open" reads as the wrong data rather than
  # the wrong heading.
  printf "\n  %-6s %-6s %-8s %-21s %-15s %s\n" "KIND" "#" "STATE" "EPIC" "DECISION" "TARGET"
  printf "  %s\n" "-------------------------------------------------------------------"
  untriaged=0
  while read -r num _ kind state decision target epic _ _; do
    [[ "${decision}" == "Untriaged" ]] && untriaged=$(( untriaged + 1 ))
    printf "  %-6s %-6s %-8s %-21s %-15s %s\n" \
      "${kind}" "#${num}" "${state}" "${epic}" "${decision//_/ }" "${target//_/ }"
  done < <(sort -k3,3 -k1,1n <<< "${board}")
  echo ""
  echo "  untriaged: ${untriaged} of $(wc -l <<< "${board}" | tr -d ' ')"
  exit 0
fi

# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

today="$(date -u +%Y-%m-%d)"

set_field() {
  local item_id="${1}" field="${2}"; shift 2
  # stdin is closed on every gh call inside a loop: the loops are fed by a here
  # string, and a child that reads stdin would eat the remaining rows.
  gh project item-edit --id "${item_id}" --project-id "${project_id}" \
    --field-id "${field}" "$@" >/dev/null </dev/null
}

info "reading open issues and pull requests from ${UPSTREAM_REPO}"

# One line per open upstream item: "<number> <kind> <title>". Pull requests are
# listed separately because the issues endpoint reports them as issues, which
# would give every pull request the wrong Kind.
#
# A list truncated at the limit is worse than an error: the items past it look
# closed to the reconciliation pass below, which would mark them closed on the
# board while upstream still has them open. The limit is therefore checked.
readonly UPSTREAM_LIMIT=500
upstream_issues="$(gh issue list --repo "${UPSTREAM_REPO}" --state open \
  --limit "${UPSTREAM_LIMIT}" --json number,title --jq '.[] | "\(.number) Issue \(.title)"')"
upstream_prs="$(gh pr list --repo "${UPSTREAM_REPO}" --state open \
  --limit "${UPSTREAM_LIMIT}" --json number,title --jq '.[] | "\(.number) PR \(.title)"')"

for listed in "${upstream_issues}" "${upstream_prs}"; do
  [[ "$(wc -l <<< "${listed}" | tr -d ' ')" -ge "${UPSTREAM_LIMIT}" ]] && \
    emergency "an upstream listing hit the ${UPSTREAM_LIMIT}-item limit and may be truncated; raise UPSTREAM_LIMIT"
done

upstream_open="$(sort -n <<< "${upstream_issues}"$'\n'"${upstream_prs}" | sed '/^$/d')"

[[ -z "${upstream_open}" ]] && emergency "upstream returned no open items; refusing to treat that as 'all closed'"

info "upstream has $(wc -l <<< "${upstream_open}" | tr -d ' ') open item(s)"

created=0
refreshed=0
closed_now=0

while read -r num kind title; do
  if on_board "${num}"; then
    item_id="$(board_field "${num}" 2)"
    # A row matched by its title rather than its number is a half-created item
    # from an interrupted run. Putting the number back is what stops the next
    # run creating a duplicate for it.
    if [[ "$(board_field "${num}" 9)" == "repair" ]]; then
      warning "${kind} #${num} was missing its Upstream number; repairing"
      set_field "${item_id}" "${FIELD_UPSTREAM}" --number "${num}"
      set_field "${item_id}" "${FIELD_KIND}" --single-select-option-id "$(option_id "Kind" "${kind}")"
      # Seeded only if still unset. Somebody may have triaged the orphan while
      # it was invisible to this script, and Fork decision is never overwritten.
      if [[ "$(board_field "${num}" 5)" == "-" ]]; then
        set_field "${item_id}" "${FIELD_DECISION}" --single-select-option-id "$(option_id "Fork decision" "Untriaged")"
      fi
    fi
    # Already open on the board: the only derived field that can have changed is
    # the state, if a previous run had marked it closed and upstream reopened it.
    if [[ "$(board_field "${num}" 4)" != "open" ]]; then
      set_field "${item_id}" "${FIELD_STATE}" --single-select-option-id "$(option_id "Upstream state" "open")"
    fi
    set_field "${item_id}" "${FIELD_SYNCED}" --date "${today}"
    refreshed=$(( refreshed + 1 ))
    continue
  fi

  item_id="$(gh project item-create "${number}" --owner "${PROJECT_OWNER}" \
    --title "[${kind} #${num}] ${title}" \
    --body "https://github.com/${UPSTREAM_REPO}/$( [[ "${kind}" == "PR" ]] && echo pull || echo issues )/${num}" \
    --format json --jq '.id' </dev/null)"

  set_field "${item_id}" "${FIELD_UPSTREAM}" --number "${num}"
  set_field "${item_id}" "${FIELD_KIND}" --single-select-option-id "$(option_id "Kind" "${kind}")"
  set_field "${item_id}" "${FIELD_STATE}" --single-select-option-id "$(option_id "Upstream state" "open")"
  set_field "${item_id}" "${FIELD_DECISION}" --single-select-option-id "$(option_id "Fork decision" "Untriaged")"
  set_field "${item_id}" "${FIELD_SYNCED}" --date "${today}"
  info "added ${kind} #${num}: ${title}"
  created=$(( created + 1 ))
done <<< "${upstream_open}"

# Anything on the board that upstream no longer lists as open has been closed or
# merged since the last run. Its state is asked for one item at a time, which is
# only as expensive as the number of items that changed.
while read -r num item_id kind state _ _ _ _ _; do
  [[ -z "${num}" ]] && continue
  [[ "${state}" != "open" ]] && continue
  grep -qE "^${num} " <<< "${upstream_open}" && continue

  if [[ "${kind}" == "PR" ]]; then
    merged="$(gh api "repos/${UPSTREAM_REPO}/pulls/${num}" --jq '.merged' 2>/dev/null </dev/null || echo "")"
    [[ "${merged}" == "true" ]] && new_state="merged" || new_state="closed"
  else
    new_state="closed"
  fi

  set_field "${item_id}" "${FIELD_STATE}" --single-select-option-id "$(option_id "Upstream state" "${new_state}")"
  set_field "${item_id}" "${FIELD_SYNCED}" --date "${today}"
  warning "${kind} #${num} is now ${new_state} upstream"
  closed_now=$(( closed_now + 1 ))
done <<< "${board}"

echo ""
info "added: ${created}"
info "refreshed: ${refreshed}"
[[ "${closed_now}" -gt 0 ]] && warning "newly closed or merged upstream: ${closed_now} (re-check their Fork decision)"
info "board: https://github.com/orgs/${PROJECT_OWNER}/projects/${number}"
success "sync complete"
