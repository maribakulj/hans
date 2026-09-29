"""A/B of the width-learning candidates against their own incumbents.

    .venv/bin/python tools/ab_gap_widths.py campaign.json --strict

Five arms over the same manufactured cases (whole line, one cache per ALTO,
like ``hans.campaign``):

1. ``proportional``  -- saknussemm's shipping geometry, the incumbent
2. ``learned/alto``  -- proportional, weights = glyph widths learned from
                        the page's own word boxes, cross-fitted by parity
3. ``ctc``           -- ``CTCCutsResolver``, the H1 candidate, unchanged
4. ``ctc+cuts``      -- ``WeightedCTCCutsResolver``: gaps weighted by widths
                        learned from the recogniser's own cuts (the branch)
5. ``ctc+alto``      -- gaps weighted by the ALTO-learned widths of arm 2

Three comparisons, each judged by the frozen H1 rule (``hans.verdict``):
2 vs 1, 4 vs 3, 5 vs 3. The rule was written for CTC-vs-proportional; it is
reused here unchanged because it is the only criterion this repository has
that was fixed before anyone measured, and because a candidate that cannot
halve its incumbent's tail without worsening its worst case is not a
candidate under any rule this project would accept.

Also printed, per comparison: how many boundaries the candidate MOVED at
all. A gap-only method can only act where the alignment left a gap, and if
that is three boundaries in three thousand, no verdict on the tail means
anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hans.alto import ReferenceLine, read_lines
from hans.corrupt import MergeCase, line_cases
from hans.cuts import LineCuts, support, transfer
from hans.geometry import GeometryRequest, WordBox
from hans.measure import Report, Resolver, boundary_errors, score_many
from hans.resolvers import (
    CTCCutsResolver,
    ProportionalResolver,
    WeightedCTCCutsResolver,
)
from hans.verdict import CorpusOutcome, decide
from hans.widths import LearnedWidthResolver


class CTCWithAltoWidths(CTCCutsResolver):
    """Arm 5: the base CTC resolver, gaps divided by ALTO-learned widths.

    Same anchors, same fallback, same support threshold as arm 3. The
    widths come from ``LearnedWidthResolver`` so they are cross-fitted the
    same way arm 2 is: never from the line being resolved.
    """

    def __init__(self, cuts: dict[str, LineCuts], widths: LearnedWidthResolver):
        super().__init__(cuts, name="ctc + alto widths")
        self._widths = widths

    def resolve(self, request: GeometryRequest) -> tuple[WordBox, ...]:
        read = self._cuts[request.line_id]
        if support(read, "".join(request.tokens)) < self.MIN_SUPPORT:
            self.declined += 1
            return self._fallback.resolve(request)  # type: ignore[attr-defined,no-any-return]
        rel: Mapping[str, float] = self._widths.model_for(request.line_id).relative()
        return transfer(
            read, request.tokens, request.hpos, request.width, char_widths=rel
        )


ARMS = ("proportional", "learned/alto", "ctc", "ctc+cuts", "ctc+alto")
COMPARISONS = (
    ("learned/alto", "proportional"),
    ("ctc+cuts", "ctc"),
    ("ctc+alto", "ctc"),
)


def _arms(lines: list[ReferenceLine], cuts: Path) -> dict[str, Resolver]:
    alto_widths = LearnedWidthResolver(lines)
    return {
        "proportional": ProportionalResolver(),
        "learned/alto": alto_widths,
        "ctc": CTCCutsResolver.from_cache(cuts),
        "ctc+cuts": WeightedCTCCutsResolver.from_cache(cuts),
        "ctc+alto": CTCWithAltoWidths(
            CTCCutsResolver.from_cache(cuts)._cuts, alto_widths
        ),
    }


def _moved(a: Resolver, b: Resolver, cases: list[MergeCase]) -> tuple[int, int]:
    """(boundaries where a and b disagree, boundaries scored)."""
    moved = total = 0
    for case in cases:
        try:
            ea = boundary_errors(a.resolve(case.request()), case)
            eb = boundary_errors(b.resolve(case.request()), case)
        except Exception:  # noqa: BLE001, S112 -- counted by score_many
            continue
        total += len(ea)
        moved += sum(1 for x, y in zip(ea, eb) if abs(x - y) > 1e-9)
    return moved, total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ab_gap_widths")
    parser.add_argument("config", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    if args.strict:
        try:
            import saknussemm.formats.alto.rewriter  # noqa: F401
        except ImportError:
            print("refus de mesurer : saknussemm absent (parite non epinglee)")
            return 2

    spec = json.loads(args.config.read_text(encoding="utf-8"))
    root = Path(spec.get("root", ".")).expanduser()
    reports: dict[str, dict[str, Report]] = {}
    moved: dict[str, dict[tuple[str, str], tuple[int, int]]] = {}

    for name, entries in spec["corpora"].items():
        groups: dict[str, list[tuple[Resolver, list[MergeCase]]]] = {
            a: [] for a in ARMS
        }
        mv: dict[tuple[str, str], list[int]] = {c: [0, 0] for c in COMPARISONS}
        missing = 0
        for e in entries:
            alto, cuts = root / e["alto"], root / e["cuts"]
            if not cuts.exists():
                missing += 1
                continue
            lines = read_lines(alto)
            cases = line_cases(lines)
            if not cases:
                continue
            arms = _arms(lines, cuts)
            for a in ARMS:
                groups[a].append((arms[a], cases))
            for cand, base in COMPARISONS:
                m, t = _moved(arms[cand], arms[base], cases)
                mv[(cand, base)][0] += m
                mv[(cand, base)][1] += t
        if missing == len(entries):
            print(f"\n=== {name} : aucun cache, corpus saute")
            continue
        print(
            f"\n=== {name}"
            + (f"  ({missing} fichier(s) sans cache, ignores)" if missing else "")
        )
        reports[name] = {a: score_many(groups[a], a) for a in ARMS}
        for a in ARMS:
            print("   ", reports[name][a].line())
        declined = sum(getattr(r, "declined", 0) for r, _ in groups["ctc"])
        print(f"    lignes declinees par le ctc (repli) : {declined}")
        moved[name] = {c: (v[0], v[1]) for c, v in mv.items()}

    for cand, base in COMPARISONS:
        print("\n" + "=" * 78)
        print(f"{cand} contre {base} -- critere gele de H1, incumbent = {base}")
        for name, mv2 in moved.items():
            m, t = mv2[(cand, base)]
            print(f"    {name:<26} frontieres deplacees : {m}/{t}")
        outcomes = [
            CorpusOutcome(name, reports[name][base], reports[name][cand])
            for name in reports
        ]
        print(decide(outcomes).report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
