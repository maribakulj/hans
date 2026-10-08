"""Run both resolvers over several corpora and let the frozen rule decide.

    python -m hans.campaign campaigns/h1.json --strict

A campaign file lists, per corpus, the ALTO files and the cut cache that goes
with each. One cache per ALTO and never a merged one: ``37-GT-BNL`` carries
509 lines under 40 distinct IDs, so pooling its caches would hand half the
lines another page's geometry, and would do it silently.

Nothing here decides anything. It measures, hands the reports to
``hans.verdict.decide``, and prints what comes back.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from hans.alto import read_lines
from hans.corrupt import MergeCase, line_cases
from hans.measure import Report, Resolver, score_many
from hans.resolvers import CTCCutsResolver, ProportionalResolver
from hans.verdict import CorpusOutcome, decide


@dataclass(frozen=True)
class Corpus:
    name: str
    pairs: tuple[tuple[Path, Path], ...]

    @classmethod
    def load(cls, name: str, entries: list[dict[str, str]], root: Path) -> Corpus:
        return cls(
            name=name,
            pairs=tuple(
                ((root / e["alto"]).expanduser(), (root / e["cuts"]).expanduser())
                for e in entries
            ),
        )


def _groups(
    corpus: Corpus,
) -> tuple[
    list[tuple[Resolver, list[MergeCase]]], list[tuple[Resolver, list[MergeCase]]], int
]:
    baseline: list[tuple[Resolver, list[MergeCase]]] = []
    candidate: list[tuple[Resolver, list[MergeCase]]] = []
    declined = 0
    for alto, cuts in corpus.pairs:
        cases = line_cases(read_lines(alto))
        if not cases:
            continue
        # The ALTO sits beside the cache in the campaign file: a cache that
        # carries a provenance block is held to it; a historical one loads
        # with a warning rather than silently (contre-revue du 7/10/2026).
        ctc = CTCCutsResolver.from_cache(cuts, alto=alto, require_provenance=False)
        baseline.append((ProportionalResolver(), cases))
        candidate.append((ctc, cases))
        declined += 0  # counted after the run
    return baseline, candidate, declined


def run(corpus: Corpus) -> tuple[Report, Report, int]:
    baseline, candidate, _ = _groups(corpus)
    base = score_many(baseline, "proportional (saknussemm)")
    cand = score_many(candidate, "ctc cuts (catmus-print)")
    declined = sum(getattr(r, "declined", 0) for r, _ in candidate)
    return base, cand, declined


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hans.campaign")
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="refuse to measure unless saknussemm pins the baseline copy",
    )
    args = parser.parse_args(argv)

    if args.strict:
        from hans.parity import ParityBroken, require_parity

        try:
            print(require_parity().line())
        except ParityBroken as exc:
            print(f"refus de mesurer : {exc}")
            return 2

    spec = json.loads(args.config.read_text(encoding="utf-8"))
    root = Path(spec.get("root", ".")).expanduser()
    outcomes = []
    for name, entries in spec["corpora"].items():
        corpus = Corpus.load(name, entries, root)
        base, cand, declined = run(corpus)
        print(f"\n=== {name}")
        print("   ", base.line())
        print("   ", cand.line())
        print(f"    lignes declinees (repli sur la ligne de base) : {declined}")
        outcomes.append(CorpusOutcome(name, base, cand))

    print("\n" + "=" * 78)
    print(decide(outcomes).report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
