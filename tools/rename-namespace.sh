#!/usr/bin/env bash
#
# Rewrite the collection namespace in a *copy* of the tree.
#
# This fork tracks grafana/grafana-ansible-collection closely, so the working
# tree keeps saying "grafana.grafana" and the rename happens at build time.
# That keeps `git merge upstream/main` conflict-free: none of the 51 files
# holding the FQCN are modified in-tree.
#
# Usage: tools/rename-namespace.sh <target-namespace> <directory>
#        tools/rename-namespace.sh --expected-count
#        tools/rename-namespace.sh --rsync-excludes
#
# The directory MUST be a throwaway copy. This script refuses to run against a
# git working tree.
#
# This script owns the list of paths that are not collection content
# (EXCLUDE_DIRS / EXCLUDE_FILES). `make dist` asks for it via --rsync-excludes
# so the copy, the rewrite, and the count assertion can never disagree about
# which files are in scope.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

readonly SOURCE_NAMESPACE="grafana"
readonly COLLECTION_NAME="grafana"

# The rewrite rule, shared by the rewrite and by the counting that asserts it.
#
# The negative lookbehind is load-bearing. "community.grafana.grafana_datasource"
# contains "grafana.grafana" as a substring:
#
#   community.grafana.grafana_datasource
#            └──────┬──────┘
#           matches "grafana.grafana"
#
# A naive s/grafana\.grafana/<ns>.grafana/g turns that into
# "community.<ns>.grafana_datasource", a collection that does not exist. Those
# two references live in runtime code (roles/grafana/tasks/datasources.yml and
# dashboards.yml), so the build would succeed and a consumer's playbook would
# fail.
#
# perl, not sed: BSD and GNU sed disagree on \b and neither supports lookbehind.
readonly MATCH_REGEX="(?<!community\\.)\\b${SOURCE_NAMESPACE}\\.${COLLECTION_NAME}\\b"

# Paths that are not collection content. Excluded from the copy, and therefore
# from the rewrite and the count. This mirrors galaxy.yml's build_ignore plus
# the two paths git and the build itself own, so build/src is close to what
# actually ships.
#
# tools/ and openspec/ matter more than they look: both contain the string
# "grafana.grafana" in prose, and counting them would make the assertion below
# drift every time this script or a spec is edited.
readonly EXCLUDE_DIRS=(
  ".git"
  "node_modules"
  "build"
  "openspec"
  "tools"
  ".github"
  ".claude"
  ".agent"
)

readonly EXCLUDE_FILES=(
  "Makefile"
  "Pipfile"
  "Pipfile.lock"
  "package.json"
  "yarn.lock"
  # Release documentation deliberately discusses both namespaces. Rewriting it
  # would turn "grafana.grafana -> indigo423.grafana" into
  # "indigo423.grafana -> indigo423.grafana" and destroy the explanation.
  "RELEASING.md"
)

# Number of occurrences the rewrite is expected to replace.
#
# Derivation, over collection content only (EXCLUDE_DIRS/EXCLUDE_FILES applied):
#
#   total                       grep -rIo "grafana\.grafana" .            = 91
#   minus community-prefixed    grep -rIo "community\.grafana\.grafana" . =  2
#   minus excluded changelogs   grep -Io "grafana\.grafana" \
#                                 CHANGELOG.rst changelogs/changelog.yaml =  6
#                                                                          ----
#   expected rewrites                                                        83
#
# After merging upstream, re-derive with:
#
#   ./tools/rename-namespace.sh --expected-count
#
# If the number moved, upstream added or removed FQCN references. Read the diff
# before updating this constant: a new "community.grafana.*" reference or a new
# way of spelling the collection name may need MATCH_REGEX adjusted, not just
# the count bumped.
readonly EXPECTED_REWRITES=83

# Files whose "grafana.grafana" references record what upstream released rather
# than referring to this collection. Rewriting them would attribute upstream's
# history to a namespace that did not exist at the time.
readonly RENAME_EXCLUDES=(
  "CHANGELOG.rst"
  "changelogs/changelog.yaml"
)

# grepExcludes
# -----------------------------------
# Emit the grep --exclude-dir / --exclude arguments for the non-content paths.
# -----------------------------------
grepExcludes() {
  local entry
  for entry in "${EXCLUDE_DIRS[@]}"; do
    echo "--exclude-dir=${entry}"
  done
  for entry in "${EXCLUDE_FILES[@]}"; do
    echo "--exclude=${entry}"
  done
}

# rsyncExcludes
# -----------------------------------
# Emit the rsync --exclude arguments for the non-content paths, so `make dist`
# copies exactly the set this script expects to rewrite.
# -----------------------------------
rsyncExcludes() {
  local entry
  for entry in "${EXCLUDE_DIRS[@]}" "${EXCLUDE_FILES[@]}"; do
    echo "--exclude=/${entry}"
  done
}

# collectFiles
# -----------------------------------
# Print the files under a directory that hold a rewritable occurrence, with the
# changelog exclusions removed.
# -----------------------------------
collectFiles() {
  local dir="${1}"
  local file relative exclude
  local -a excludes=()
  local line
  # bash 3.2, still the default on macOS, has no mapfile
  while IFS= read -r line; do excludes+=("${line}"); done < <(grepExcludes)

  grep -rIl "${excludes[@]}" \
    -e "${SOURCE_NAMESPACE}\\.${COLLECTION_NAME}" "${dir}" 2>/dev/null \
    | while IFS= read -r file; do
        relative="${file#"${dir}"/}"
        for exclude in "${RENAME_EXCLUDES[@]}"; do
          if [[ "${relative}" == "${exclude}" ]]; then
            continue 2
          fi
        done
        echo "${file}"
      done
}

# countMatches
# -----------------------------------
# Count occurrences of a regex across the given files.
# `grep -o` cannot do this job: it prints only the matched text, discarding the
# "community." prefix the exclusion depends on.
# -----------------------------------
countMatches() {
  local regex="${1}"
  shift
  if [[ "$#" -eq 0 ]]; then
    echo "0"
    return
  fi
  perl -ne "\$count += () = /${regex}/g; END { print \$count + 0 }" "$@"
}

# rewriteFiles
# -----------------------------------
# Perform the substitution in place and print the number of substitutions perl
# actually made. That number, not a before/after difference, is the evidence the
# assertion checks: once rewritten, "<ns>.grafana.grafana" (the grafana role's
# own FQCN) still matches MATCH_REGEX, so differencing would undercount.
# -----------------------------------
rewriteFiles() {
  local namespace="${1}"
  shift
  local countFile
  countFile="$(mktemp)"

  perl -pi -e "\$count += s/${MATCH_REGEX}/${namespace}.${COLLECTION_NAME}/g; \
    END { open(my \$fh, '>', '${countFile}'); print \$fh \$count + 0; close(\$fh) }" \
    "$@"

  cat "${countFile}"
  rm -f "${countFile}"
}

# reportExpectedCount
# -----------------------------------
# Print the expected rewrite count derived from the current working tree, so
# EXPECTED_REWRITES can be refreshed after an upstream merge.
# -----------------------------------
reportExpectedCount() {
  local total community changelogs
  local -a excludes=()
  local line
  # bash 3.2, still the default on macOS, has no mapfile
  while IFS= read -r line; do excludes+=("${line}"); done < <(grepExcludes)

  total="$(grep -rIo "${excludes[@]}" \
    -e "${SOURCE_NAMESPACE}\\.${COLLECTION_NAME}" . | wc -l | tr -d ' ')"
  community="$(grep -rIo "${excludes[@]}" \
    -e "community\\.${SOURCE_NAMESPACE}\\.${COLLECTION_NAME}" . | wc -l | tr -d ' ')"
  changelogs="$(grep -Io -e "${SOURCE_NAMESPACE}\\.${COLLECTION_NAME}" \
    "${RENAME_EXCLUDES[@]}" | wc -l | tr -d ' ')"

  echo "total occurrences      : ${total}"
  echo "community.grafana.*    : ${community}  (must remain untouched)"
  echo "in excluded changelogs : ${changelogs}  (not rewritten)"
  echo "expected rewrites      : $(( total - community - changelogs ))"
  echo ""
  echo "EXPECTED_REWRITES in this script is currently ${EXPECTED_REWRITES}"
}

if [[ "${1:-}" == "--expected-count" ]]; then
  reportExpectedCount
  exit 0
fi

if [[ "${1:-}" == "--rsync-excludes" ]]; then
  rsyncExcludes
  exit 0
fi

targetNamespace="${1:-}"
targetDir="${2:-}"

if [[ -z "${targetNamespace}" ]] || [[ -z "${targetDir}" ]]; then
  echo >&2 "usage: tools/rename-namespace.sh <target-namespace> <directory>"
  echo >&2 "       tools/rename-namespace.sh --expected-count"
  exit 1
fi

heading "Grafana Ansible Collection" "Renaming namespace to ${targetNamespace}"

if [[ ! -d "${targetDir}" ]]; then
  emergency "directory does not exist: ${targetDir}"
fi

# Refuse to touch a git working tree. The whole point of the build-time rename
# is that the tree is never modified.
if [[ -e "${targetDir}/.git" ]]; then
  emergency "refusing to rewrite a git working tree: ${targetDir}"
fi

# make sure perl exists
if [[ "$(command -v perl)" = "" ]]; then
  echo >&2 "perl command is required for the namespace rewrite";
  exit 1;
fi

renameFiles=()
while IFS= read -r line; do renameFiles+=("${line}"); done < <(collectFiles "${targetDir}")

if [[ "${#renameFiles[@]}" -eq 0 ]]; then
  emergency "no files to rewrite; is ${targetDir} a copy of the collection?"
fi

before="$(countMatches "${MATCH_REGEX}" "${renameFiles[@]}")"
info "found ${before} in-scope occurrences in ${#renameFiles[@]} files"

rewrites="$(rewriteFiles "${targetNamespace}" "${renameFiles[@]}")"
info "rewrote ${rewrites} occurrences"

# The changelog title labels future output rather than recording the past, so
# unlike the changelog bodies it does get rewritten.
perl -pi -e "s/^title: .*\$/title: \\u${targetNamespace}.\\u${COLLECTION_NAME}/" \
  "${targetDir}/changelogs/config.yaml"

# The namespace field is what Galaxy authorizes the publish against. name and
# version are deliberately left alone: the version mirrors upstream and is the
# single source of truth for the release tag check.
perl -pi -e "s/^namespace: .*\$/namespace: ${targetNamespace}/" \
  "${targetDir}/galaxy.yml"

if [[ "${rewrites}" -ne "${EXPECTED_REWRITES}" ]]; then
  error "expected ${EXPECTED_REWRITES} rewrites, performed ${rewrites}"
  error "upstream likely changed the FQCN references; run:"
  error "  ./tools/rename-namespace.sh --expected-count"
  emergency "rewrite count assertion failed"
fi

# Residual check. The regex must also ignore the freshly written namespace:
# "indigo423.grafana.grafana" is the correct rendering of the grafana role's own
# FQCN, and it still contains "grafana.grafana".
readonly RESIDUAL_REGEX="(?<!community\\.)(?<!${targetNamespace}\\.)\\b${SOURCE_NAMESPACE}\\.${COLLECTION_NAME}\\b"
residual="$(countMatches "${RESIDUAL_REGEX}" "${renameFiles[@]}")"

if [[ "${residual}" -ne 0 ]]; then
  error "${residual} occurrences of ${SOURCE_NAMESPACE}.${COLLECTION_NAME} remain:"
  grep -In -e "${SOURCE_NAMESPACE}\\.${COLLECTION_NAME}" "${renameFiles[@]}" >&2 || true
  emergency "namespace rewrite incomplete"
fi

# The community.grafana.grafana_* references must have survived verbatim.
if grep -rIq --exclude-dir=.git -e "community\\.${targetNamespace}\\." "${targetDir}"; then
  error "the rewrite corrupted a community.grafana reference:"
  grep -rIn --exclude-dir=.git -e "community\\.${targetNamespace}\\." "${targetDir}" >&2
  emergency "community.grafana references must not be rewritten"
fi

success "namespace rewritten to ${targetNamespace}.${COLLECTION_NAME} (${rewrites} occurrences)"
