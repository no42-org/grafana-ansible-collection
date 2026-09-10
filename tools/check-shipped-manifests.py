"""Check what the published collection claims about its own dependencies.

Two independent checks, both invoked by tools/lint-release.sh.

1. The declared Python dependencies match what the code actually imports.

   Derived from source rather than maintained by hand, and it fails in BOTH
   directions. An undeclared import is the obvious defect. A declaration with
   no corresponding import is the one that produced this check: the root
   requirements.txt shipped `yamllint`, `ansible-lint` and `pylint` to
   consumers for years, and a check that only asked "is every import declared?"
   would have passed it.

2. No manifest in the published artifact names a development-only tool.

   Checked against the built tarball, not the tree, because the question is
   never "is this string in the repository" but "does the published artifact
   claim it". Inspecting the artifact validates build_ignore at the same time:
   remove an exclusion and a repository-facing manifest reappears here.

   This is a denylist, so it is a second line of defence behind check 1 rather
   than the primary control. A missing entry fails open.

No shebang and not executable, deliberately. `ansible-test sanity`'s shebang
test scans the whole tree, including tools/, and rejects a non-module .py file
carrying one. tools/lint-release.sh invokes this as `python3 <path>`, so the
shebang was decoration; suppressing the sanity test with tests/sanity/ignore-*
is ruled out by the release-pipeline spec, which requires sanity to stay a real
blocking gate.
"""

from __future__ import annotations

import ast
import re
import sys
import tarfile
from pathlib import Path

# Import name -> distribution name, for the cases where they differ (`yaml` is
# published as `PyYAML`). Empty of real entries today because this collection
# imports only `requests`, which is both. It exists so the first genuine
# mismatch is a one-line addition rather than a redesign.
IMPORT_TO_DISTRIBUTION: dict[str, str] = {}

# Manifests that are addressed to a consumer and therefore constrain what the
# collection may claim. tests/integration/requirements.txt is deliberately
# absent: `ansible-test integration` can run from an installed collection, so
# its dependencies have a plausible audience.
CONSUMER_MANIFEST = "requirements.txt"

# Development-only tools. If one of these appears in a shipped manifest, the
# manifest is addressed to the wrong audience.
DEVELOPER_TOOLS = frozenset(
    {
        "ansible-lint",
        "black",
        "editorconfig-checker",
        "flake8",
        "isort",
        "markdownlint",
        "markdownlint-cli2",
        "molecule",
        "mypy",
        "pylint",
        "pytest",
        "pytest-testinfra",
        "ruff",
        "testinfra",
        "textlint",
        "tox",
        "yamllint",
        "zizmor",
    }
)


def fail(message: str) -> None:
    print(f"    \033[31m\033[1m[error]\033[0m {message}", file=sys.stderr)


def third_party_imports(plugins: Path) -> tuple[dict[str, set[str]], int]:
    """Top-level third-party imports under plugins/, mapped to their files.

    Returns the imports and a status. A file that cannot be parsed makes the
    status non-zero rather than being skipped: an unparseable plugin means the
    derived set is incomplete, and reporting an error while exiting 0 is the
    exact defect these gates exist to prevent.
    """
    found: dict[str, set[str]] = {}
    status = 0
    for path in sorted(plugins.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError as exc:
            fail(f"{path}: could not parse, so its imports are unknown: {exc}")
            status = 1
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules = [node.module]
            else:
                continue
            for module in modules:
                top = module.split(".")[0]
                if top in sys.stdlib_module_names:
                    continue
                if top.startswith("ansible") or top == "__future__":
                    continue
                found.setdefault(IMPORT_TO_DISTRIBUTION.get(top, top), set()).add(str(path))
    return found, status


def parse_requirements(text: str) -> set[str]:
    """Distribution names declared in a pip requirements file."""
    declared = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~\[;\s]", line, maxsplit=1)[0].strip()
        if name:
            declared.add(name)
    return declared


def check_declarations_match_code(root: Path) -> int:
    """Check 1: the declared set equals the derived set."""
    print("  ‣ declared Python dependencies match what plugins/ imports")
    manifest = root / CONSUMER_MANIFEST
    if not manifest.is_file():
        fail(f"{CONSUMER_MANIFEST} is missing; the collection's Python dependencies are undeclared")
        return 1

    imported, status = third_party_imports(root / "plugins")
    declared = parse_requirements(manifest.read_text())

    for name in sorted(set(imported) - declared):
        where = sorted(imported[name])[0]
        fail(
            f"{name} is imported by {where} but not declared in {CONSUMER_MANIFEST}; "
            f"a module reporting missing_required_lib('{name}') would point at nothing"
        )
        status = 1
    for name in sorted(declared - set(imported)):
        fail(
            f"{name} is declared in {CONSUMER_MANIFEST} but nothing under plugins/ imports it; "
            "a consumer-facing manifest states only what the collection needs at run time"
        )
        status = 1

    if status == 0:
        print(f"    {CONSUMER_MANIFEST} declares exactly {sorted(declared) or '[]'}")
    return status


def shipped_manifests(root: Path) -> tuple[dict[str, str], str]:
    """Manifest contents from the built tarball, or from the tree as a fallback.

    Returns the contents and a description of the surface inspected, so the
    check can say what it actually looked at rather than passing silently on a
    surface it did not.
    """
    tarballs = sorted((root / "build" / "dist").glob("*.tar.gz"))
    if tarballs:
        tarball = tarballs[-1]
        contents = {}
        with tarfile.open(tarball) as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                if not re.search(r"requirements[^/]*\.(txt|yml)$", member.name):
                    continue
                handle = archive.extractfile(member)
                if handle is not None:
                    contents[member.name] = handle.read().decode("utf-8", "replace")
        return contents, f"the built artifact {tarball.name}"

    # No tarball. Evaluate the tree against build_ignore instead, and say so.
    import fnmatch

    try:
        import yaml
    except ImportError:  # pragma: no cover
        fail("PyYAML is required to read galaxy.yml's build_ignore")
        return {}, "nothing"
    ignore = yaml.safe_load((root / "galaxy.yml").read_text()).get("build_ignore", [])
    contents = {}
    for path in sorted(root.rglob("requirements*.txt")) + sorted(root.rglob("requirements*.yml")):
        rel = str(path.relative_to(root))
        if rel.startswith(("build/", "node_modules/", ".venv/", ".ansible/", "ansible_collections/")):
            continue
        # build_ignore patterns are matched by ansible-galaxy as globs, but a
        # bare directory name like `tests/roles` excludes everything under it,
        # so treat each pattern as a prefix too. Without this the fallback
        # over-collects, which is the safe direction but reports a count that
        # does not match the artifact.
        if any(
            fnmatch.fnmatch(rel, pattern)
            or rel == pattern
            or rel.startswith(pattern.rstrip("/*") + "/")
            for pattern in ignore
        ):
            continue
        contents[rel] = path.read_text()
    return contents, "the working tree evaluated against galaxy.yml's build_ignore (no tarball found)"


def check_no_developer_tools(root: Path) -> int:
    """Check 2: no shipped manifest names a development-only tool."""
    manifests, surface = shipped_manifests(root)
    print(f"  ‣ no developer tool in a shipped manifest, per {surface}")
    if not manifests:
        fail("no shipped manifest was inspected; the check cannot pass on nothing")
        return 1

    status = 0
    for name, text in sorted(manifests.items()):
        for entry in parse_requirements(text):
            if entry.lower() in DEVELOPER_TOOLS:
                fail(
                    f"{name} names the development-only tool {entry!r}; "
                    "a manifest inside the collection is addressed to a consumer"
                )
                status = 1
    if status == 0:
        print(f"    {len(manifests)} shipped manifest(s), none naming a developer tool")
    return status


def main() -> int:
    root = Path.cwd()
    return check_declarations_match_code(root) | check_no_developer_tools(root)


if __name__ == "__main__":
    sys.exit(main())
