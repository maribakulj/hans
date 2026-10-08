"""Les défauts relevés en contre-revue le 7 octobre 2026, chacun pinné.

Chaque test reproduit d'abord le contre-exemple exécuté par le relecteur,
puis affirme le comportement corrigé.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hans.alto import ReferenceLine, read_page_lines
from hans.corrupt import line_case, line_case_in_its_box
from hans.cuts import ImpossibleRequest, LineCuts, transfer
from hans.geometry import WordBox
from hans.measure import Report
from hans.reproject import reproject, reproject_lines
from hans.resolvers import CTCCutsResolver, InkSnapResolver
from hans.resolvers.ctc import CacheMismatch
from hans.verdict import CorpusOutcome, Outcome, decide

# 4. InkSnapResolver relaie « dernier recours »


def test_the_ink_wrapper_relays_last_resort() -> None:
    inner = CTCCutsResolver({}, last_resort=True)
    assert InkSnapResolver(inner, {}).last_resort is True
    assert InkSnapResolver(CTCCutsResolver({}), {}).last_resort is False


# 1. Le verdict n'est pas déclarable sur des populations incomparables


def _report(within: float, boundaries: int, failures: int = 0) -> Report:
    return Report("r", 100, boundaries, failures, 0.0, 0.0, 0.0, 10.0, 0.0, within)


def test_ninety_nine_failures_and_one_good_boundary_do_not_confirm() -> None:
    """100 cas, 99 exceptions, une réponse juste : CONFIRMED avant."""
    outcomes = [
        CorpusOutcome(str(i), _report(0.80, 100), _report(1.0, 1, failures=99))
        for i in range(3)
    ]
    v = decide(outcomes)
    assert v.outcome is Outcome.REFUTED
    assert "echecs candidat: 99" in v.report()


def test_a_few_declined_lines_do_not_make_the_verdict_undeclarable() -> None:
    """Un résolveur de dernier recours décline 1 à 4 lignes par corpus (H1) :
    ce sont des frontières ratées, pas une interdiction de comparer."""
    outcomes = [
        CorpusOutcome(str(i), _report(0.80, 8090), _report(0.95, 8086, failures=4))
        for i in range(3)
    ]
    assert decide(outcomes).outcome is Outcome.CONFIRMED


def test_a_candidate_that_answered_nothing_cannot_take_part_in_a_verdict() -> None:
    outcomes = [
        CorpusOutcome(str(i), _report(0.80, 100), _report(0.95, 100)) for i in range(2)
    ]
    outcomes.append(
        CorpusOutcome("muet", _report(0.80, 100), _report(0.0, 0, failures=100))
    )
    v = decide(outcomes)
    assert v.outcome is Outcome.INCOMPLETE
    assert "aucune frontiere" in v.reason


def test_an_empty_corpus_cannot_take_part_in_a_verdict() -> None:
    outcomes = [
        CorpusOutcome(str(i), _report(0.80, 100), _report(0.95, 100)) for i in range(2)
    ]
    outcomes.append(CorpusOutcome("vide", _report(0.0, 0), _report(0.0, 0)))
    v = decide(outcomes)
    assert v.outcome is Outcome.INCOMPLETE
    assert "vide" in v.reason


def test_same_populations_still_decide_as_before() -> None:
    outcomes = [
        CorpusOutcome(str(i), _report(0.80, 100), _report(0.95, 100)) for i in range(3)
    ]
    assert decide(outcomes).outcome is Outcome.CONFIRMED


# 3. La reprojection dit ce qu'elle n'a pas su garantir


def test_a_line_split_in_two_is_reported_as_merged() -> None:
    r = reproject(["abc", "def"], ["abc", "de", "f"])
    assert list(r.lines) == reproject_lines(["abc", "def"], ["abc", "de", "f"])
    assert r.merged == (1,)
    assert not r.ok


def test_permuted_lines_are_reported_not_silently_cut() -> None:
    r = reproject(["alpha beta", "gamma delta"], ["gamma delta", "alpha beta"])
    assert not r.ok
    assert 0 in r.suspect and 1 in r.suspect


def test_the_untouched_control_is_ok() -> None:
    src = ["Maisiepenfois quel'vne", "& l'autre eftoient des"]
    assert reproject(src, src).ok


# 8. PAGE : la transcription de référence est celle d'index 0


def test_page_reader_takes_text_equiv_index_zero_whatever_the_xml_order(
    tmp_path: Path,
) -> None:
    def word(identity: str, x0: int, x1: int) -> str:
        return (
            f'<Word id="{identity}"><Coords points="{x0},0 {x1},0 {x1},20 {x0},20"/>'
            '<TextEquiv index="1"><Unicode>alternative</Unicode></TextEquiv>'
            '<TextEquiv index="0"><Unicode>correct</Unicode></TextEquiv>'
            "</Word>"
        )

    page = tmp_path / "page.xml"
    page.write_text(
        '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">'
        '<Page><TextRegion id="r1"><TextLine id="l1">'
        '<Coords points="0,0 100,0 100,20 0,20"/>'
        + word("w1", 0, 40)
        + word("w2", 50, 100)
        + "</TextLine></TextRegion></Page></PcGts>",
        encoding="utf-8",
    )
    lines = read_page_lines(page)
    assert [w.text for w in lines[0].words] == ["correct", "correct"]


# 9. Une demande impossible est déclinée, pas dessinée hors du rectangle


def test_three_tokens_in_one_pixel_are_declined() -> None:
    read = LineCuts("L1", "a b", ((0, 1), (1, 2), (2, 3)))
    with pytest.raises(ImpossibleRequest):
        transfer(read, ("a", " ", "b"), 0, 1)


def test_a_declined_request_counts_as_a_failure_in_the_bench() -> None:
    from hans.corrupt import MergeCase
    from hans.measure import score

    resolver = CTCCutsResolver({"L1": LineCuts("L1", "a b", ((0, 1), (1, 2), (2, 3)))})
    case = MergeCase(
        "L1",
        0,
        "ab",
        ("a", " ", "b"),
        (WordBox("a", 0, 1), WordBox("b", 1, 1)),
        ((1, 1),),
        0,
        1,
    )
    report = score(resolver, [case])
    assert report.failures == 1 and report.boundaries == 0


# 7. Le scénario « ligne entière » peut porter le vrai rectangle de la ligne


_LINE = ReferenceLine(
    line_id="L1",
    hpos=0,
    vpos=300,
    width=200,
    height=40,
    words=(WordBox("de", 20, 30), WordBox("la", 100, 30)),
)


def test_line_case_keeps_the_union_and_the_line_box_variant_keeps_the_line() -> None:
    union = line_case(_LINE)
    assert union is not None
    assert (union.box_hpos, union.box_width) == (20, 110)
    assert (union.request().vpos, union.request().height) == (0, 0)
    whole = line_case_in_its_box(_LINE)
    assert whole is not None
    assert (whole.box_hpos, whole.box_width) == (0, 200)
    assert (whole.request().vpos, whole.request().height) == (300, 40)
    assert whole.gaps == union.gaps


def test_a_line_box_that_does_not_contain_its_words_falls_back_to_the_union() -> None:
    narrow = ReferenceLine("L1", 50, 0, 20, 0, _LINE.words)
    case = line_case_in_its_box(narrow)
    assert case is not None and (case.box_hpos, case.box_width) == (20, 110)


# 5. Un cache sans la bonne provenance est refusé à l'ouverture


def _cache(tmp_path: Path, provenance: dict[str, object] | None) -> Path:
    payload: dict[str, object] = {
        "alto": "page.xml",
        "lines": {
            "L1": {"text": "de la", "spans": [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5]]}
        },
    }
    if provenance is not None:
        payload["provenance"] = provenance
    path = tmp_path / "cuts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_cache_from_another_alto_is_refused_when_the_alto_is_given(
    tmp_path: Path,
) -> None:
    alto = tmp_path / "page.xml"
    alto.write_bytes(b"<alto/>")
    path = _cache(tmp_path, {"schema": 2, "alto": {"sha256": "0" * 64}})
    with pytest.raises(CacheMismatch, match="alto digest"):
        CTCCutsResolver.from_cache(path, alto=alto)


def test_a_cache_without_provenance_cannot_be_verified(tmp_path: Path) -> None:
    alto = tmp_path / "page.xml"
    alto.write_bytes(b"<alto/>")
    with pytest.raises(CacheMismatch, match="no provenance"):
        CTCCutsResolver.from_cache(_cache(tmp_path, None), alto=alto)
    # unchanged: nothing to verify against, the historical caches still load
    assert len(CTCCutsResolver.from_cache(_cache(tmp_path, None))) == 1


def test_a_matching_provenance_loads(tmp_path: Path) -> None:
    import hashlib

    alto = tmp_path / "page.xml"
    alto.write_bytes(b"<alto/>")
    digest = hashlib.sha256(b"<alto/>").hexdigest()
    path = _cache(tmp_path, {"schema": 2, "alto": {"sha256": digest}})
    assert len(CTCCutsResolver.from_cache(path, alto=alto)) == 1


# 6. L'outil de décodage : provenance réelle, et lignes à un seul mot


def test_cache_provenance_hashes_the_files_it_names(tmp_path: Path) -> None:
    import hashlib
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "decode_lines_under_test",
        Path(__file__).parent.parent / "tools" / "decode_lines.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    alto, image, model = tmp_path / "p.xml", tmp_path / "p.png", tmp_path / "m.mlmodel"
    alto.write_bytes(b"<alto/>")
    image.write_bytes(b"\x89PNG")
    model.write_bytes(b"model")
    prov = module.cache_provenance(
        alto, image, model, scale=1.181, image_size=(640, 480)
    )
    assert prov["schema"] == 2
    assert prov["alto"]["sha256"] == hashlib.sha256(b"<alto/>").hexdigest()
    assert prov["image"] == {
        "name": "p.png",
        "sha256": hashlib.sha256(b"\x89PNG").hexdigest(),
        "width": 640,
        "height": 480,
    }
    assert prov["model"]["sha256"] == hashlib.sha256(b"model").hexdigest()
    assert prov["scale"] == 1.181
    # and what decode_lines writes is exactly what from_cache verifies
    cache = tmp_path / "cuts.json"
    cache.write_text(json.dumps({"alto": "p.xml", "provenance": prov, "lines": {}}))
    CTCCutsResolver.from_cache(cache, alto=alto, image=image)


def test_a_historical_cache_loads_with_a_warning_when_asked_to(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    alto = tmp_path / "page.xml"
    alto.write_bytes(b"<alto/>")
    resolver = CTCCutsResolver.from_cache(
        _cache(tmp_path, None), alto=alto, require_provenance=False
    )
    assert len(resolver) == 1
    assert "no provenance block" in capsys.readouterr().err


def test_decode_lines_source_asks_the_reader_for_single_word_lines() -> None:
    """Un grep, assumé : kraken n'est pas appelable ici. Il épingle le
    paramètre, pas le décodage."""
    source = (Path(__file__).parent.parent / "tools" / "decode_lines.py").read_text()
    assert "reader(alto, min_words=1)" in source


# 10. --strict vérifie la parité, pas seulement l'import


def test_strict_runs_the_parity_battery_and_names_the_version() -> None:
    pytest.importorskip("saknussemm.formats.alto.rewriter")
    from hans.parity import require_parity

    parity = require_parity()
    assert parity.cases > 0
    assert parity.saknussemm_version


def test_strict_refuses_a_drifted_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("saknussemm.formats.alto.rewriter")
    from hans.parity import ParityBroken, require_parity
    from hans.resolvers import proportional

    monkeypatch.setattr(proportional, "compute_geometry", lambda *a: ())
    with pytest.raises(ParityBroken, match="derive"):
        require_parity()


def test_bench_strict_reports_parity(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    pytest.importorskip("saknussemm.formats.alto.rewriter")
    from hans.bench import main

    alto = tmp_path / "empty.xml"
    alto.write_text(
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"/>', encoding="utf-8"
    )
    main([str(alto), "--strict"])
    assert "parite tenue avec saknussemm" in capsys.readouterr().out
