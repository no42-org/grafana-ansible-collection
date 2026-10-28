# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command line for the upstream handover tooling.

`check` validates the manifest. `check --coverage` also lists every commit in
upstream/main..main that no chunk and no fork_only entry claims. Coverage is
separate because a squash merge changes shas, so a commit can never list
itself, and `make ci-lint-release` must pass without it.

`rebuild` rebases each review branch onto its new base into a local
handover-candidate branch and writes the state file. It exits 1 if any chunk
conflicted, 2 if it could not run at all (a dirty work tree, a missing ref).
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import manifest  # noqa: E402
import promote as promoter  # noqa: E402
import rebuild as rebuilder  # noqa: E402
import state  # noqa: E402

HERE = Path(__file__).resolve().parent


def unassigned(loaded: manifest.Manifest, repo: Path, main: str, upstream: str) -> list[str]:
    listed = manifest.git(repo, "rev-list", "--no-merges", f"{upstream}..{main}")
    if listed.returncode != 0:
        raise manifest.ManifestError(f"cannot list {upstream}..{main}: {listed.stderr.strip()}")
    return [sha for sha in listed.stdout.split() if sha not in loaded.all_commits()]


def check(args: argparse.Namespace) -> int:
    try:
        loaded = manifest.load(args.manifest, args.repo, args.main)
        missing = unassigned(loaded, args.repo, args.main, args.upstream) if args.coverage else []
    except manifest.ManifestError as err:
        print(f"handover: {err}", file=sys.stderr)
        return 1
    print(f"{len(loaded.chunks)} chunks, {len(loaded.fork_only)} fork-only")
    if missing:
        print(f"{len(missing)} commits in {args.upstream}..{args.main} are in no chunk:")
        for sha in missing:
            subject = manifest.git(args.repo, "log", "-1", "--format=%s", sha).stdout.strip()
            print(f"  {sha} {subject}")
        return 1
    return 0


def rebuild(args: argparse.Namespace) -> int:
    try:
        loaded = manifest.load(args.manifest, args.repo, args.main)
    except manifest.ManifestError as err:
        print(f"handover: {err}", file=sys.stderr)
        return 1
    previous = {}
    if args.previous is not None and args.previous.exists():
        previous = state.load(args.previous)
    try:
        states = rebuilder.rebuild(loaded, args.repo, args.upstream, args.origin)
    except rebuilder.RebuildError as err:
        print(f"handover: {err}", file=sys.stderr)
        return 2
    for cid, current in states.items():
        if cid in previous:
            current.verified_at = previous[cid].verified_at
            current.last_good = previous[cid].last_good
    state.save(args.out, states)
    return 1 if any(s.rebase == "conflict" for s in states.values()) else 0


def _states_and_manifest(args: argparse.Namespace):
    try:
        loaded = manifest.load(args.manifest, args.repo, args.main)
    except manifest.ManifestError as err:
        print(f"handover: {err}", file=sys.stderr)
        return None, None
    return loaded, state.load(args.state)


def matrix(args: argparse.Namespace) -> int:
    loaded, states = _states_and_manifest(args)
    if loaded is None:
        return 1
    print(json.dumps({"include": promoter.matrix(loaded, states)}, separators=(",", ":")))
    return 0


def test(args: argparse.Namespace) -> int:
    try:
        loaded = manifest.load(args.manifest, args.repo, args.main)
    except manifest.ManifestError as err:
        print(f"handover: {err}", file=sys.stderr)
        return 1
    chunk = next((c for c in loaded.chunks if c.id == args.chunk), None)
    if chunk is None:
        print(f"handover: unknown chunk {args.chunk}", file=sys.stderr)
        return 1
    passed = promoter.run_tests(chunk, args.repo)
    args.results.mkdir(parents=True, exist_ok=True)
    (args.results / f"{chunk.id}.json").write_text(
        json.dumps({"chunk": chunk.id, "passed": passed}) + "\n")
    return 0 if passed else 1


def read_results(directory: Path) -> dict[str, bool]:
    results = {}
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        data = json.loads(path.read_text())
        results[data["chunk"]] = bool(data["passed"])
    return results


def promote(args: argparse.Namespace) -> int:
    loaded, states = _states_and_manifest(args)
    if loaded is None:
        return 1
    sha = manifest.git(args.repo, "rev-parse", "--verify", f"{args.upstream}^{{commit}}")
    if sha.returncode != 0:
        print(f"handover: {args.upstream} does not exist", file=sys.stderr)
        return 2
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    states = promoter.promote(loaded, states, read_results(args.results), today,
                              sha.stdout.strip(), args.origin, args.repo)
    state.save(args.state, states)
    wanted = [c.id for c in loaded.chunks if states[c.id].rebase == "ok" and not states[c.id].landed]
    return 1 if any(not states[cid].promoted for cid in wanted) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="validate the manifest")
    p.add_argument("--manifest", type=Path, default=HERE / "chunks.yml")
    p.add_argument("--repo", type=Path, default=HERE.parent.parent)
    p.add_argument("--main", default="main")
    p.add_argument("--upstream", default="upstream/main")
    p.add_argument("--coverage", action="store_true")
    p.set_defaults(func=check)
    p = sub.add_parser("rebuild", help="rebase review branches into handover candidates")
    p.add_argument("--manifest", type=Path, default=HERE / "chunks.yml")
    p.add_argument("--repo", type=Path, default=HERE.parent.parent)
    p.add_argument("--main", default="main")
    p.add_argument("--upstream", default="upstream/main")
    p.add_argument("--origin", default="origin")
    p.add_argument("--previous", type=Path, help="the previously published state.json")
    p.add_argument("--out", type=Path, default=HERE.parent.parent / "build/handover/state.json")
    p.set_defaults(func=rebuild)
    default_state = HERE.parent.parent / "build/handover/state.json"
    default_results = HERE.parent.parent / "build/handover/results"
    for name, func, helptext in (("matrix", matrix, "print the CI test matrix as JSON"),
                                 ("test", test, "run one chunk's tests in this checkout"),
                                 ("promote", promote, "push passing candidates to review/*")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--manifest", type=Path, default=HERE / "chunks.yml")
        p.add_argument("--repo", type=Path, default=HERE.parent.parent)
        p.add_argument("--main", default="main")
        p.add_argument("--state", type=Path, default=default_state)
        p.set_defaults(func=func)
        if name != "matrix":
            p.add_argument("--results", type=Path, default=default_results)
        if name == "test":
            p.add_argument("--chunk", required=True)
        if name == "promote":
            p.add_argument("--upstream", default="upstream/main")
            p.add_argument("--origin", default="origin")
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
