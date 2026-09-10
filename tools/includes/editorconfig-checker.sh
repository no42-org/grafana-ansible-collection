#!/usr/bin/env bash
#
# Provisions the standalone editorconfig-checker binary, pinned.
#
# The Node package `editorconfig-checker@5.0.1` was used before. It downloads a
# platform binary at install time and ships none for darwin-arm64, and when it
# cannot find one it prints a stack trace and **exits 0**:
#
#   Error: ENOENT: no such file or directory, scandir
#     '.../node_modules/editorconfig-checker/bin/latest/bin'
#   exit=0
#
# So `make ci-lint-editorconfig` reported success on any Apple Silicon machine
# without checking a single file. lint-gates requires that a gate fail when its
# linter cannot run, and a wrapper that swallows its own crash cannot satisfy
# that. The standalone Go binary has no such wrapper.
#
# Pinned here, in one place. Same pattern as shellcheck and actionlint.

readonly EDITORCONFIG_CHECKER_VERSION="4.0.1"

# editorconfigCheckerBin
#
# Echoes a path to the pinned binary, downloading it into tools/bin on first
# use. Fails loudly rather than falling back to an unpinned copy on PATH: an
# unpinned linter is a gate that can change what it demands without anyone
# changing the repository.
editorconfigCheckerBin() {
  local binDir bin
  binDir="$(pwd)/tools/bin"
  bin="${binDir}/editorconfig-checker-${EDITORCONFIG_CHECKER_VERSION}"

  if [[ -x "${bin}" ]]; then
    echo "${bin}"
    return 0
  fi

  local os arch asset
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "${os}" in
    darwin) asset="editorconfig-checker-darwin-all.tar.gz" ;;
    linux)
      case "${arch}" in
        x86_64)          asset="editorconfig-checker-linux-amd64.tar.gz" ;;
        aarch64 | arm64) asset="editorconfig-checker-linux-arm64.tar.gz" ;;
        *) echo >&2 "TOOLCHAIN NOT INSTALLED: no editorconfig-checker build for linux/${arch}"; return 1 ;;
      esac
      ;;
    *) echo >&2 "TOOLCHAIN NOT INSTALLED: no editorconfig-checker build for ${os}"; return 1 ;;
  esac

  local url="https://github.com/editorconfig-checker/editorconfig-checker/releases/download"
  url="${url}/v${EDITORCONFIG_CHECKER_VERSION}/${asset}"

  mkdir -p "${binDir}"
  local tmp
  tmp="$(mktemp -d)"
  if ! curl -fsSL "${url}" -o "${tmp}/ec.tar.gz"; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: could not download ${url}"
    rm -rf "${tmp}"
    return 1
  fi
  if ! tar -xzf "${tmp}/ec.tar.gz" -C "${tmp}"; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: could not unpack ${asset}"
    rm -rf "${tmp}"
    return 1
  fi

  local extracted
  extracted="$(find "${tmp}" -type f -name 'editorconfig-checker*' ! -name '*.tar.gz' ! -name '*.json' | head -1)"
  if [[ -z "${extracted}" ]]; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: no binary inside ${asset}"
    rm -rf "${tmp}"
    return 1
  fi

  mv "${extracted}" "${bin}"
  chmod +x "${bin}"
  rm -rf "${tmp}"
  echo "${bin}"
}
