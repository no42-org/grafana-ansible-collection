"""Compare each role's pinned version against the upstream project's latest release.

Roles pin the version they install rather than resolving `latest` at run time, so
a role's behaviour cannot change without a commit. The cost of that is a pin
nobody moves: `opentelemetry_collector` sat at 0.90.1, released 2023-12-01,
until upstream reached 0.160.0, because nothing asked anyone to move it. This is
the thing that asks.

Run by .github/workflows/role-versions.yml on a schedule, which turns whatever
this reports into one pull request per behind role. The bump is then verified by
the role-test matrix before it can merge -- which is the point. An unverified
bump moves the risk rather than removing it.

Two failure modes this deliberately avoids:

  Reporting "up to date" when it could not look. A rate limit, a network
  failure or a renamed repository all fail the run instead. A quiet tracker and
  an up-to-date repository both produce no pull requests, and this repository
  has twice shipped a check whose silence was mistaken for success.

  Inferring tag conventions. grafana/mimir tags releases `mimir-3.2.1`, not
  `v3.2.1`. That lives in the table below rather than in a regex that happens to
  cope today.

No shebang, and not executable: `ansible-test sanity`'s shebang test scans
tools/ and rejects a non-module .py carrying one. Invoked as `python3 <path>`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# role -> (defaults file, version variable, upstream repo, tag prefixes to strip)
#
# Tracked roles only. The one exclusion is deliberate and is listed in
# EXCLUDED below rather than being absent without explanation.
TRACKED: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "loki": ("roles/loki/defaults/main.yml", "loki_version", "grafana/loki", ("v",)),
    "mimir": ("roles/mimir/defaults/main.yml", "mimir_version", "grafana/mimir", ("mimir-", "v")),
    "tempo": ("roles/tempo/defaults/main.yml", "tempo_version", "grafana/tempo", ("v",)),
    "alloy": ("roles/alloy/defaults/main.yml", "alloy_version", "grafana/alloy", ("v",)),
    "opentelemetry_collector": (
        "roles/opentelemetry_collector/defaults/main.yml",
        "otel_collector_version",
        "open-telemetry/opentelemetry-collector-releases",
        ("v",),
    ),
}

# Not tracked, for a reason that will not change on its own. It is still
# pinned; the exclusion is from the automated bump, not from having a version.
EXCLUDED: dict[str, str] = {
    "grafana": (
        "installs through a package manager, not a release download: the "
        "version becomes grafana-<v> on RHEL and grafana=<v> on Debian, which "
        "package repositories serve on their own schedule and retention. Its "
        "pin is maintained by hand; see RELEASING.md."
    ),
}


def fail(message: str) -> None:
    print(f"    \033[31m\033[1m[error]\033[0m {message}", file=sys.stderr)


def pinned_version(defaults: Path, variable: str) -> str | None:
    m = re.search(rf'^{re.escape(variable)}: *"?([^"\n#]*)', defaults.read_text(), re.M)
    return m.group(1).strip() if m else None


def latest_release(repo: str, strip: tuple[str, ...]) -> str:
    """Upstream's latest release tag, with the known prefixes removed.

    Raises rather than returning a sentinel. A lookup that fails must fail the
    run; "could not determine" is not "no update available".
    """
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "role-version-check"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        tag = json.load(response)["tag_name"]
    for prefix in strip:
        if tag.startswith(prefix):
            return tag[len(prefix):]
    # A tag that matches none of the known prefixes means the project changed
    # its convention. Guessing here is how a comparison silently goes wrong.
    raise ValueError(f"{repo}: tag {tag!r} matches none of the expected prefixes {strip}")


def main() -> int:
    root = Path.cwd()
    status = 0
    behind: list[dict[str, str]] = []

    print("  ‣ pinned role versions against upstream")
    for role, (defaults, variable, repo, strip) in sorted(TRACKED.items()):
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
            upstream = latest_release(repo, strip)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError) as exc:
            # Explicitly not "no update available".
            fail(f"{role}: could not determine the latest release of {repo}: {exc}")
            status = 1
            continue

        state = "current" if current == upstream else f"BEHIND -> {upstream}"
        print(f"    {role:26} pinned {current:12} upstream {upstream:12} {state}")
        if current != upstream:
            behind.append(
                {"role": role, "defaults": defaults, "variable": variable,
                 "current": current, "upstream": upstream, "repo": repo}
            )

    for role, reason in sorted(EXCLUDED.items()):
        print(f"    {role:26} not tracked: {reason.split(';')[0].split('--')[0].strip()}")

    # Consumed by the workflow to decide what to open.
    out = os.environ.get("ROLE_VERSION_REPORT")
    if out:
        Path(out).write_text(json.dumps(behind, indent=2) + "\n")

    if status == 0 and not behind:
        print(f"    all {len(TRACKED)} tracked role(s) are current")
    return status


if __name__ == "__main__":
    sys.exit(main())
