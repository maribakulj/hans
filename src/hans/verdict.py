"""H1's verdict, computed rather than judged.

The criterion below was fixed on 2026-09-21, in ``AUTOPILOT.md``, before a
single line of CTC existed -- and before anyone knew whether it was
reachable. It is transcribed here so that declaring H1 is an arithmetic
operation on two reports and not an act of interpretation by whoever ran the
campaign.

That matters more than usual here. The maintainer authorised the loop to
declare the verdict unsupervised (2026-09-21), which removes the one reader
who could have said "that looks too good". What replaces that reader is
this module: the thresholds cannot be renegotiated at the moment of
measuring, because they are not re-derived at the moment of measuring.

The FROZEN part is the RULE, not the numbers. Baseline figures are recomputed
from the same manufactured cases as the candidate on every run, so the two
sides are always compared on identical material -- a baseline pasted in as a
constant would silently stop matching the corpus it was measured on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hans.measure import Report

#: Verbatim from AUTOPILOT.md, 2026-09-21. Changing this string is changing
#: the experiment; a test pins it.
FROZEN_CRITERION = (
    "Le CTC reduit de moitie la part des frontieres au-dela de 0,5 caractere "
    "sur au moins deux corpus sur trois, et n'aggrave le pire cas sur aucun."
)

#: Float representation slack, nothing more. ``within_half_char`` is a ratio
#: of counts over thousands of boundaries, so its real resolution is ~1e-4;
#: 1e-9 is far below anything measurable and exists only so that a candidate
#: that halves the share EXACTLY is not refused by the last bit of a double.
#: Widening this would be moving the threshold, which rule 7 forbids.
_FLOAT_SLACK = 1e-9

#: "deux corpus sur trois" is not satisfiable with two corpora. Declaring H1
#: on fewer is refused mechanically rather than left to judgement.
REQUIRED_CORPORA = 3


class Outcome(Enum):
    CONFIRMED = "confirmee"
    REFUTED = "refutee"
    INCOMPLETE = "non declarable"


def _beyond_half(report: Report) -> float:
    return 1.0 - report.within_half_char


@dataclass(frozen=True)
class CorpusOutcome:
    """One corpus, both resolvers, same cases."""

    corpus: str
    baseline: Report
    candidate: Report

    @property
    def comparable(self) -> str | None:
        """Why the two reports cannot be compared, or ``None`` when they can.

        The rule halves a SHARE. A share over a hundred boundaries and a
        share over one are not the same quantity: a candidate that raised
        on 99 cases out of 100 and placed its single surviving boundary
        well used to CONFIRM (contre-revue du 7/10/2026). Failures are
        counted by ``measure`` and then excluded from the distribution, so
        the only honest reading is to refuse the comparison when the two
        sides did not score the same boundaries, or scored none.
        """
        if self.baseline.boundaries == 0 or self.candidate.boundaries == 0:
            return "corpus vide"
        if self.candidate.boundaries != self.baseline.boundaries:
            return (
                f"populations incomparables : {self.candidate.boundaries} "
                f"frontieres contre {self.baseline.boundaries} "
                f"({self.candidate.failures} echec(s) du candidat, "
                f"{self.baseline.failures} de la reference)"
            )
        return None

    @property
    def halved(self) -> bool:
        """Did the candidate halve the share of boundaries beyond 0.5 char?"""
        target = _beyond_half(self.baseline) / 2
        return _beyond_half(self.candidate) <= target + _FLOAT_SLACK

    @property
    def worst_not_worse(self) -> bool:
        """A method that fixes the middle and wrecks the tail has not won.

        The tail is the whole point: a boundary 3.8 characters out is a box
        drawn around the wrong word, and that is the failure this project
        exists to repair.
        """
        return self.candidate.worst <= self.baseline.worst + _FLOAT_SLACK

    def line(self) -> str:
        return (
            f"{self.corpus:<26} "
            f"au-dela 0.5car: {_beyond_half(self.baseline):6.2%} -> "
            f"{_beyond_half(self.candidate):6.2%}  "
            f"(cible {_beyond_half(self.baseline) / 2:6.2%})  "
            f"{'OK ' if self.halved else 'NON'}   "
            f"pire: {self.baseline.worst:.1f} -> {self.candidate.worst:.1f}  "
            f"{'OK' if self.worst_not_worse else 'AGGRAVE'}"
        )


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    reason: str
    corpora: tuple[CorpusOutcome, ...]

    def report(self) -> str:
        head = "\n".join(c.line() for c in self.corpora)
        return f"{head}\n\nH1 {self.outcome.value.upper()} -- {self.reason}"


def decide(outcomes: list[CorpusOutcome]) -> Verdict:
    """Apply the frozen criterion. No arguments to tune, on purpose."""
    corpora = tuple(outcomes)

    if len(corpora) < REQUIRED_CORPORA:
        return Verdict(
            Outcome.INCOMPLETE,
            f"{len(corpora)} corpus mesure(s), {REQUIRED_CORPORA} exiges par "
            "le critere gele. H1 ne peut pas etre declaree.",
            corpora,
        )

    incomparable = [(c.corpus, c.comparable) for c in corpora if c.comparable]
    if incomparable:
        return Verdict(
            Outcome.INCOMPLETE,
            "; ".join(f"{corpus} : {why}" for corpus, why in incomparable)
            + ". H1 ne peut pas etre declaree.",
            corpora,
        )

    aggravated = [c.corpus for c in corpora if not c.worst_not_worse]
    if aggravated:
        return Verdict(
            Outcome.REFUTED,
            f"le pire cas est aggrave sur {', '.join(aggravated)} : le critere "
            "l'interdit sur tout corpus, quel que soit le gain moyen.",
            corpora,
        )

    halved = [c.corpus for c in corpora if c.halved]
    if len(halved) >= 2:
        return Verdict(
            Outcome.CONFIRMED,
            f"part au-dela de 0,5 caractere reduite de moitie sur "
            f"{len(halved)}/{len(corpora)} corpus ({', '.join(halved)}), "
            "pire cas jamais aggrave.",
            corpora,
        )

    return Verdict(
        Outcome.REFUTED,
        f"reduction de moitie atteinte sur {len(halved)}/{len(corpora)} corpus "
        "seulement ; le critere en exige deux.",
        corpora,
    )
