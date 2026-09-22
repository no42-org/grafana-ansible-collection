"""Check that the versions the documentation claims are the versions the roles pin.

A pin lives in `roles/<role>/defaults/main.yml` and nowhere else, but it is
written down in two more places a consumer actually reads: a badge in the root
README.md, and the default documented in that role's own README.md. Nothing
compared the three, so they drifted -- and the drift is invisible from inside a
bump, because the bump rewrites the pin and the documentation says whatever it
said yesterday.

Six claims were stale when this was written, across three roles and several
bumps: the root badges for grafana, loki and opentelemetry_collector, the table
rows in roles/grafana/ and roles/opentelemetry_collector/README.md, and
roles/loki/README.md, which still documented `loki_version: "latest"` -- the
opposite of what this fork does.

The role table is imported from tools/check-role-versions.py rather than copied.
Two lists of which roles exist and where their pins live is exactly the kind of
second definition this repository keeps being bitten by.

Fails in both directions, like tools/check-shipped-manifests.py:

  - a documented version that is not the pin, and
  - a role with no badge at all, because a role that quietly drops out of the
    documentation is how a stale claim becomes an absent one.

A claim inside a role README is checked when it is there and not required,
because those files are inherited and several of them never named a version.

`--fix` rewrites every stale claim to the pin, which is what
tools/bump-role-versions.sh calls so a bump pull request lands complete rather
than half-applied.

No shebang and not executable, for the reason given in
tools/check-shipped-manifests.py: `ansible-test sanity` rejects a non-module
.py file that carries one.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_README = ROOT / "README.md"

# A version as these projects write one: 1.19.2, 13.2.2, 0.161.0.
VERSION = r"\d+\.\d+\.\d+"


def tracked_roles() -> dict[str, dict[str, object]]:
    """The role table from check-role-versions.py, imported rather than copied.

    The file name has a dash in it, so it cannot be imported by name.
    """
    path = ROOT / "tools" / "check-role-versions.py"
    spec = importlib.util.spec_from_file_location("check_role_versions", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TRACKED


def pinned_version(defaults: Path, variable: str) -> str:
    """The pin, read from the role's defaults file."""
    match = re.search(
        rf'^{re.escape(variable)}: *"?({VERSION})"?$',
        defaults.read_text(),
        flags=re.M,
    )
    if match is None:
        raise SystemExit(f"{defaults}: no {variable} pin of the form X.Y.Z")
    return match.group(1)


def badge_pattern(role: str) -> re.Pattern[str]:
    """The shields.io badge for a role. Underscores are doubled in a badge label."""
    return re.compile(
        rf"(img\.shields\.io/badge/{re.escape(role.replace('_', '__'))}-)({VERSION})(-)"
    )


def readme_claims(text: str, variable: str) -> list[tuple[int, str]]:
    """Versions a role README states as the default, as (line number, version).

    Two shapes, because the inherited READMEs do not agree on one: a table row
    whose first cell is the variable, and a yaml block assigning it.

    The line has to *state* the default, not merely mention the variable. A
    sentence such as "skipped when alloy_version is below 1.9.0" names both a
    variable and a version and claims nothing about what the role installs;
    read loosely, it reports a stale pin that is not there.

    Within a qualifying line the claim is the last version on it, which is
    where all three shapes put the value. The alloy row mentions "1.4.2" first
    as an example of the accepted format.
    """
    assignment = re.compile(rf'^\s*{re.escape(variable)}\s*:\s*"?({VERSION})"?\s*$')
    claims: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        direct = assignment.match(line)
        if direct:
            claims.append((number, direct.group(1)))
            continue
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] != variable:
            continue
        found = re.findall(VERSION, line)
        if found:
            claims.append((number, found[-1]))
    return claims


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="rewrite stale claims to the pin instead of reporting them",
    )
    args = parser.parse_args()

    roles = tracked_roles()
    root_text = ROOT_README.read_text()
    problems: list[str] = []
    fixed: list[str] = []

    print("  ‣ documented versions against the pins the roles install")

    for role, entry in sorted(roles.items()):
        defaults = ROOT / str(entry["defaults"])
        variable = str(entry["variable"])
        pin = pinned_version(defaults, variable)

        # The root README badge. Required: every role has one, and a role that
        # loses its badge has lost the only version statement a reader meets
        # before the roles themselves.
        pattern = badge_pattern(role)
        match = pattern.search(root_text)
        if match is None:
            problems.append(
                f"README.md: no version badge for {role}; "
                f"the pin is {pin} and nothing in the root README says so"
            )
        elif match.group(2) != pin:
            if args.fix:
                root_text = pattern.sub(rf"\g<1>{pin}\g<3>", root_text, count=1)
                fixed.append(f"README.md: {role} badge {match.group(2)} -> {pin}")
            else:
                problems.append(
                    f"README.md: the {role} badge says {match.group(2)}, "
                    f"{defaults.relative_to(ROOT)} pins {pin}"
                )

        # The role's own README. Optional: several inherited ones never name a
        # version, and inventing a row for them is not this check's business.
        role_readme = ROOT / "roles" / role / "README.md"
        if not role_readme.is_file():
            continue
        role_text = role_readme.read_text()
        for number, claimed in readme_claims(role_text, variable):
            if claimed == pin:
                continue
            if args.fix:
                lines = role_text.splitlines(keepends=True)
                index = number - 1
                # Only the last version on the line, which is the claim.
                head, sep, tail = lines[index].rpartition(claimed)
                lines[index] = head + pin + tail if sep else lines[index]
                role_text = "".join(lines)
                fixed.append(
                    f"roles/{role}/README.md:{number}: {claimed} -> {pin}"
                )
            else:
                problems.append(
                    f"roles/{role}/README.md:{number}: documents {variable} "
                    f"as {claimed}, {defaults.relative_to(ROOT)} pins {pin}"
                )
        if args.fix and role_text != role_readme.read_text():
            role_readme.write_text(role_text)

    if args.fix:
        if root_text != ROOT_README.read_text():
            ROOT_README.write_text(root_text)
        for line in fixed:
            print(f"    {line}")
        if not fixed:
            print("    every documented version already matches its pin")
        return 0

    for line in problems:
        print(f"    \033[31m\033[1m[error]\033[0m {line}", file=sys.stderr)
    if problems:
        print(f"    {len(problems)} documented version(s) disagree with a pin")
        return 1
    print(f"    all {len(roles)} tracked role(s) documented at their pinned version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
