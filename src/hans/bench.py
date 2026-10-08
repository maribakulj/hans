"""Run every resolver over a corpus and print one line each.

    python -m hans.bench ~/cinoc/corpus/BnF-bpt6k3265015q/X0000002.xml

Reads ALTO, manufactures merge cases, scores each registered resolver, and
prints the distribution. No model, no network, no credentials -- which is
the point: this is the loop's engine, and an engine that needs a GPU to
answer "did anything get worse" is one the loop cannot start.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from hans.alto import read_lines
from hans.corrupt import cases_from_lines, line_cases
from hans.measure import Resolver, score
from hans.resolvers import ProportionalResolver


def registered() -> list[Resolver]:
    """Every resolver the bench knows about.

    The CTC resolver joins this list at G2 and only if H1 says it should.
    """
    return [ProportionalResolver()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hans.bench")
    parser.add_argument("alto", nargs="+", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "refuse to measure unless saknussemm is importable, so the "
            "baseline's parity test can actually have run here"
        ),
    )
    parser.add_argument(
        "--run",
        type=int,
        default=0,
        help=(
            "adjacent words glued per case; 0 (default) = the WHOLE line, "
            "which is what the rewriter's slow path really redistributes"
        ),
    )
    args = parser.parse_args(argv)

    if args.strict:
        from hans.parity import ParityBroken, require_parity

        try:
            print(require_parity().line())
        except ParityBroken as exc:
            print(f"refus de mesurer : {exc}")
            return 2

    lines = []
    for path in args.alto:
        found = read_lines(path)
        print(f"{path.name}: {len(found)} scorable lines")
        lines.extend(found)

    if args.run == 0:
        cases = line_cases(lines)
        window = "whole line"
    else:
        cases = cases_from_lines(lines, run=args.run)
        window = f"run={args.run}"
    print(f"\n{len(cases)} cases ({window}), {len(lines)} lines\n")
    if not cases:
        print("nothing to score")
        return 1

    for resolver in registered():
        print(score(resolver, cases).line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
