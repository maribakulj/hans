"""Remettre un texte corrigé sur ses lignes : ce que ça doit garantir."""

from __future__ import annotations

from hans.reproject import reproject_lines

SRC = ["Maisiepenfois quel'vne", "& l'autre eftoient des", "dons de l'elprit"]


def test_the_empty_control_returns_the_source_untouched() -> None:
    """Reprojeter un texte NON corrigé doit rendre la source à l'identique.

    C'est le seul test qui attrape une erreur de découpe sans dépendre d'un
    modèle : si la reprojection déforme quoi que ce soit, elle le déforme
    aussi ici. Mesuré sur le corpus : 251/251.
    """
    assert reproject_lines(SRC, SRC) == SRC


def test_a_word_split_does_not_lose_its_line() -> None:
    """Le cas que l'alignement par jetons refuse.

    ``Maisiepenfois`` devient ``Mais ie penſois`` : aucun jeton commun, donc
    Jaccard ne vouche pas la ligne et elle garde son OCR. Au caractère, les
    lettres sont les mêmes et la ligne suit.
    """
    corrected = [
        "Mais ie penſois que l'vne",
        "& l'autre eſtoient des",
        "dons de l'eſprit",
    ]
    out = reproject_lines(SRC, corrected)
    assert len(out) == 3
    assert "penſois" in out[0]
    assert "eſtoient" in out[1]
    assert "eſprit" in out[2]


def test_fewer_returned_lines_still_fill_every_source_line() -> None:
    """Le modèle a fusionné deux lignes : la sortie garde le bon compte.

    C'est le mode de panne qui arrive sur 2 à 4 pages sur 9 en correction de
    page entière, et la raison d'être de cette reprojection.
    """
    out = reproject_lines(
        SRC, ["Mais ie penſois que l'vne & l'autre eſtoient des", "dons de l'eſprit"]
    )
    assert len(out) == len(SRC)


def test_more_returned_lines_than_asked() -> None:
    out = reproject_lines(
        SRC,
        [
            "Mais ie penſois",
            "que l'vne",
            "& l'autre eſtoient des",
            "dons de",
            "l'eſprit",
        ],
    )
    assert len(out) == len(SRC)


def test_the_cuts_never_go_backwards() -> None:
    """Monotonie : une frontière ne peut pas reculer sur la précédente.

    Sans ça une ligne pourrait recevoir du texte déjà donné à sa voisine, ce
    qui duplique au lieu de répartir.
    """
    out = reproject_lines(SRC, ["texte entierement different", "sans rapport"])
    assert len(out) == len(SRC)
    joined = "".join(out)
    assert len(joined) <= len("texte entierement different\nsans rapport")


def test_an_empty_source_is_empty() -> None:
    assert reproject_lines([], ["quoi que ce soit"]) == []
