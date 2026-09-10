#!/usr/bin/env bash
#
# The one list of directories no linter should look in, and a `find` wrapper
# that honours it.
#
# Four separate times a lint script walked the whole tree and reported findings
# in code this repository does not own:
#
#   .ansible/             29 ansible-lint findings   (ansible-lint installs here)
#   ansible_collections/  4851 ansible-lint findings (ansible.cfg: collections_paths = ./)
#   .venv/                250 yamllint findings      (uv sync)
#   .venv/, build/src/    shellcheck findings        (ansible_test's own scripts)
#
# Each was fixed in isolation, in a different file, which is why it happened
# four times. The list lives here now: when a tool is added that installs into
# the working tree, its directory goes in this array and every script that
# sources this file is covered.
#
# .yamllint, .ansible-lint and tools/rename-namespace.sh keep their own copies,
# because they are consumed by tools that read their own configuration formats
# rather than calling `find`. Those three and this one must agree.

# shellcheck disable=SC2034  # consumed by lintFind below and by sourcing scripts
readonly LINT_EXCLUDED_DIRS=(
  ".git"
  # Package manager and toolchain install targets.
  "node_modules"
  ".venv"
  ".ansible"
  "ansible_collections"
  # Build output: a rewritten copy of the tree, already linted at its source.
  "build"
  # Downloaded linter binaries.
  "bin"
  # AI tool working directories, never committed.
  "openspec"
  ".claude"
  ".agent"
)

# lintFind <find-expression...>
#
# Runs `find .` with every excluded directory pruned, then applies the caller's
# expression. Pruning rather than filtering afterwards, so a large node_modules
# or .venv is not walked at all.
#
# The caller supplies its own action, `-print` or `-print0`, because the two are
# not interchangeable and appending one here would double up on the other.
lintFind() {
  local pruneArgs=()
  local dir
  for dir in "${LINT_EXCLUDED_DIRS[@]}"; do
    pruneArgs+=(-name "${dir}" -prune -o)
  done
  find . "${pruneArgs[@]}" "$@"
}
