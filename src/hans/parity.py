"""Is the baseline copy still saknussemm's? Checked here, not assumed.

``bench --strict`` and ``campaign --strict`` used to check only that
saknussemm was *importable*. That is the wrong invariant: an importable
saknussemm whose ``_compute_geometry`` had moved on from our copy would let a
campaign run, and measure against a baseline nobody ships (contre-revue du
7/10/2026). The strict flag now runs the parity battery itself and records
which saknussemm it ran against.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The battery the parity test pins. Shared with the test so that what the
#: strict flag checks at campaign time is exactly what CI checks.
CASES: list[tuple[int, int, list[str]]] = [
    (100, 300, ["de", " ", "la", " ", "Republique"]),
    (0, 100, ["hello"]),
    (50, 500, ["a", " ", "bb", " ", "ccc", " ", "dddd"]),
    (0, 3, ["a", " ", "b", " ", "c", " ", "d"]),  # min-1 floor territory
    (7, 1, ["x", " ", "y"]),  # width smaller than the token count
    (0, 1000, [" ", "mot", " "]),
    (12, 240, ["l'", "Etat", " ", "c'est", " ", "moi"]),
    (0, 0, ["a", " ", "b"]),
    (5, 77, []),
    (0, 50, [" ", " ", "x"]),  # no-break space is NOT a separator
]

SPACE_TOKENS = [" ", "  ", "\t", "\n", " ", " ", " ", "x", "", " x"]


@dataclass(frozen=True)
class Parity:
    saknussemm_version: str
    cases: int

    def line(self) -> str:
        return (
            f"parite tenue avec saknussemm {self.saknussemm_version} ({self.cases} cas)"
        )


class ParityBroken(RuntimeError):
    """The copy drifted from the original, or the original is absent."""


def require_parity() -> Parity:
    """Raise unless the baseline copy reproduces saknussemm on the battery."""
    try:
        from saknussemm.formats.alto import rewriter
    except ImportError as exc:
        raise ParityBroken(
            "saknussemm absent : la ligne de base n'est pas epinglee. "
            "Installer l'extra [parity]."
        ) from exc
    from hans.resolvers.proportional import compute_geometry, is_space_token

    for hpos, width, tokens in CASES:
        ours = compute_geometry(hpos, width, tokens)
        theirs = rewriter._compute_geometry(hpos, width, list(tokens))
        if ours != theirs:
            raise ParityBroken(
                f"la copie a derive de saknussemm sur ({hpos}, {width}, {tokens}) : "
                f"{ours} != {theirs}"
            )
    for token in SPACE_TOKENS:
        if is_space_token(token) != rewriter._is_space_token(token):
            raise ParityBroken(f"predicat d'espace different sur {token!r}")
    try:
        from importlib.metadata import version

        installed = version("saknussemm")
    except Exception:  # noqa: BLE001 -- version is reporting, not a gate
        installed = "version inconnue"
    return Parity(installed, len(CASES) + len(SPACE_TOKENS))
