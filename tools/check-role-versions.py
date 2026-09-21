"""Compare each role's pinned version against what that role can actually install.

Roles pin the version they install rather than resolving `latest` at run time, so
a role's behaviour cannot change without a commit. The cost of that is a pin
nobody moves: `opentelemetry_collector` sat at 0.90.1, released 2023-12-01,
until upstream reached 0.160.0, because nothing asked anyone to move it. This is
the thing that asks.

Run by .github/workflows/role-versions.yml on a schedule, which turns whatever
this reports into one pull request per behind role. The bump is then verified by
the role-test matrix before it can merge -- which is the point. An unverified
bump moves the risk rather than removing it.

**Each role is asked about the source it installs from, not a source that
resembles it.** The roles do not agree on one, so neither does this:

  loki, mimir, tempo, alloy   download a .rpm or .deb asset attached to a
                              GitHub release
  opentelemetry_collector     downloads a .tar.gz asset from a GitHub release
                              of open-telemetry/opentelemetry-collector-releases
  grafana                     installs through apt.grafana.com and
                              rpm.grafana.com, where the version becomes
                              grafana=<v> or grafana-<v>

`apt.grafana.com` also carries loki, mimir, tempo and alloy, and asking it about
them would be asking about a package those roles never fetch: a version could be
present there and absent as a release asset, or the reverse. Being convenient to
query is not the same as being the thing under test.

`grafana` used to be excluded for this reason -- its releases and its packages
are different populations -- and was therefore the one pin nothing watched. The
premise was right and the conclusion was not: a package repository has an index,
and the index is exactly the list of versions that are installable.

Three failure modes this deliberately avoids:

  Reporting "up to date" when it could not look. A rate limit, a network
  failure or a renamed repository all fail the run instead. A quiet tracker and
  an up-to-date repository both produce no pull requests, and this repository
  has twice shipped a check whose silence was mistaken for success.

  Inferring tag conventions. grafana/mimir tags releases `mimir-3.2.1`, not
  `v3.2.1`. That lives in the table below rather than in a regex that happens to
  cope today.

  Proposing a version that cannot be installed. A GitHub release exists before
  its assets finish uploading, and a package repository serves its own schedule
  and retention. A release with no package for this role is reported as HELD and
  is not proposed -- printed rather than failed, because a weekly job that goes
  red for a condition that heals itself is a weekly job people stop reading.

No shebang, and not executable: `ansible-test sanity`'s shebang test scans
tools/ and rejects a non-module .py carrying one. Invoked as `python3 <path>`,
so the standard library is the whole toolbox.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from pathlib import Path

USER_AGENT = "role-version-check"
TIMEOUT = 30

# Where grafana's packages actually come from. Both are consulted and a version
# counts only if it is in both: the role tests run on both package families, so
# a pin that installs on one of them is not a pin this repository can verify.
APT_INDEX = "https://apt.grafana.com/dists/stable/main/binary-amd64/Packages"
RPM_BASE = "https://rpm.grafana.com"

# role -> how to ask, and what to ask.
#
#   kind      "release" for a GitHub release asset, "package" for a repository
#   defaults  the file holding the pin
#   variable  the pin
#   source    repo for "release", a human-readable origin for "package"; ends up
#             in the bump pull request's body either way
#   strip     release only: tag prefixes to remove, never guessed
#   artifacts release only: the suffixes this role downloads. A release missing
#             one of them is not installable by this role, whatever it says.
#   package   package only: the package name in the index
TRACKED: dict[str, dict[str, object]] = {
    "loki": {
        "kind": "release", "defaults": "roles/loki/defaults/main.yml",
        "variable": "loki_version", "source": "grafana/loki",
        "strip": ("v",), "artifacts": (".rpm", ".deb"),
    },
    "mimir": {
        "kind": "release", "defaults": "roles/mimir/defaults/main.yml",
        "variable": "mimir_version", "source": "grafana/mimir",
        "strip": ("mimir-", "v"), "artifacts": (".rpm", ".deb"),
    },
    "tempo": {
        "kind": "release", "defaults": "roles/tempo/defaults/main.yml",
        "variable": "tempo_version", "source": "grafana/tempo",
        "strip": ("v",), "artifacts": (".rpm", ".deb"),
    },
    "alloy": {
        "kind": "release", "defaults": "roles/alloy/defaults/main.yml",
        "variable": "alloy_version", "source": "grafana/alloy",
        "strip": ("v",), "artifacts": (".rpm", ".deb"),
    },
    "opentelemetry_collector": {
        "kind": "release",
        "defaults": "roles/opentelemetry_collector/defaults/main.yml",
        "variable": "otel_collector_version",
        "source": "open-telemetry/opentelemetry-collector-releases",
        "strip": ("v",), "artifacts": (".tar.gz",),
    },
    "grafana": {
        "kind": "package", "defaults": "roles/grafana/defaults/main.yml",
        "variable": "grafana_version",
        "source": "apt.grafana.com and rpm.grafana.com",
        "package": "grafana",
    },
}


def fail(message: str) -> None:
    print(f"    \033[31m\033[1m[error]\033[0m {message}", file=sys.stderr)


def held(message: str) -> None:
    print(f"    \033[33m\033[1m[held]\033[0m  {message}")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def version_key(version: str) -> tuple[int, ...]:
    """Sort key for the version shapes these projects publish.

    Numeric components only. None of the six carries a suffix that has to
    order (a prerelease never reaches these indexes), and inventing a full
    version algebra for versions that do not need one is how a comparison
    acquires a bug nobody looks for.
    """
    return tuple(int(part) for part in re.findall(r"\d+", version)[:4])


def pinned_version(defaults: Path, variable: str) -> str | None:
    m = re.search(rf'^{re.escape(variable)}: *"?([^"\n#]*)', defaults.read_text(), re.M)
    return m.group(1).strip() if m else None


def latest_release(repo: str, strip: tuple[str, ...]) -> tuple[str, list[str]]:
    """Upstream's latest release: its version, and the names of its assets.

    Raises rather than returning a sentinel. A lookup that fails must fail the
    run; "could not determine" is not "no update available".
    """
    payload = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest"))
    tag = payload["tag_name"]
    assets = [asset["name"] for asset in payload.get("assets", [])]
    for prefix in strip:
        if tag.startswith(prefix):
            return tag[len(prefix):], assets
    # A tag that matches none of the known prefixes means the project changed
    # its convention. Guessing here is how a comparison silently goes wrong.
    raise ValueError(f"{repo}: tag {tag!r} matches none of the expected prefixes {strip}")


def missing_artifacts(assets: list[str], version: str, suffixes: tuple[str, ...]) -> list[str]:
    """Which of the suffixes this role needs the release does not carry."""
    return [
        suffix for suffix in suffixes
        if not any(name.endswith(suffix) and version in name for name in assets)
    ]


def apt_versions(index_url: str, package: str) -> set[str]:
    """Versions of `package` in a Debian-style Packages index.

    Stanza-per-package, blank-line separated. Parsed as stanzas rather than by
    scanning for `Version:` lines, because every package in the file has one.
    """
    text = fetch(index_url).decode("utf-8", "replace")
    versions: set[str] = set()
    for stanza in text.split("\n\n"):
        if re.search(rf"^Package: {re.escape(package)}$", stanza, re.M):
            m = re.search(r"^Version: (.+)$", stanza, re.M)
            if m:
                versions.add(m.group(1).strip())
    if not versions:
        raise ValueError(f"no {package!r} package found in {index_url}")
    return versions


def rpm_versions(base_url: str, package: str) -> set[str]:
    """Versions of `package` in a yum repository.

    repomd.xml names the primary metadata by content hash, so the filename
    cannot be hardcoded and is read from there each time.
    """
    repomd = fetch(f"{base_url}/repodata/repomd.xml").decode("utf-8", "replace")
    m = re.search(r'<data type="primary">.*?<location href="([^"]+)"', repomd, re.S)
    if not m:
        raise ValueError(f"no primary metadata listed in {base_url}/repodata/repomd.xml")
    raw = fetch(f"{base_url}/{m.group(1)}")
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    namespace = {"c": "http://linux.duke.edu/metadata/common"}
    versions: set[str] = set()
    for pkg in ElementTree.fromstring(raw).findall("c:package", namespace):
        if pkg.findtext("c:name", default="", namespaces=namespace) == package:
            version = pkg.find("c:version", namespace)
            if version is not None and version.get("ver"):
                versions.add(version.get("ver"))
    if not versions:
        raise ValueError(f"no {package!r} package found in {base_url}")
    return versions


def latest_package(package: str) -> str:
    """The newest version present in BOTH package families.

    Both, not either. The role tests run on both, so a version only one of them
    serves is a version this repository cannot verify a bump against -- which is
    the same reason the pin exists at all.
    """
    common = apt_versions(APT_INDEX, package) & rpm_versions(RPM_BASE, package)
    if not common:
        raise ValueError(f"{package}: no version is present in both apt and rpm indexes")
    return max(common, key=version_key)


def main() -> int:
    root = Path.cwd()
    status = 0
    behind: list[dict[str, str]] = []
    holds = 0

    print("  ‣ pinned role versions against what each role installs")
    for role, spec in sorted(TRACKED.items()):
        defaults = str(spec["defaults"])
        variable = str(spec["variable"])
        source = str(spec["source"])

        current = pinned_version(root / defaults, variable)
        if current is None:
            fail(f"{role}: {variable} not found in {defaults}")
            status = 1
            continue
        if current == "latest":
            fail(f"{role}: {variable} is still 'latest'; this role is meant to be pinned")
            status = 1
            continue

        try:
            if spec["kind"] == "release":
                upstream, assets = latest_release(source, spec["strip"])  # type: ignore[arg-type]
                absent = missing_artifacts(assets, upstream, spec["artifacts"])  # type: ignore[arg-type]
                if absent:
                    # The release exists; what this role downloads from it does
                    # not. Proposing it would open a pull request whose role
                    # test cannot pass.
                    held(
                        f"{role}: {source} released {upstream} but it carries no "
                        f"{', '.join(absent)} asset; not proposing it"
                    )
                    holds += 1
                    continue
            else:
                upstream = latest_package(str(spec["package"]))
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                ValueError, TimeoutError, ElementTree.ParseError) as exc:
            # Explicitly not "no update available".
            fail(f"{role}: could not determine the newest installable version from {source}: {exc}")
            status = 1
            continue

        state = "current" if current == upstream else f"BEHIND -> {upstream}"
        print(f"    {role:26} pinned {current:12} installable {upstream:12} {state}")
        if current != upstream:
            behind.append(
                {"role": role, "defaults": defaults, "variable": variable,
                 "current": current, "upstream": upstream, "repo": source}
            )

    # Consumed by the workflow to decide what to open.
    out = os.environ.get("ROLE_VERSION_REPORT")
    if out:
        Path(out).write_text(json.dumps(behind, indent=2) + "\n")

    if status == 0 and not behind:
        if holds:
            print(f"    {len(TRACKED) - holds} role(s) current, {holds} held; see above")
        else:
            print(f"    all {len(TRACKED)} tracked role(s) are current")
    return status


if __name__ == "__main__":
    sys.exit(main())
