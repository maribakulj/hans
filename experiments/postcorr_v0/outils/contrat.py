"""Contrat de sortie commun (§7) : éditions non chevauchantes avec offsets dans la ligne source ; texte corrigé dérivé."""
from dataclasses import dataclass, field
from rapidfuzz.distance import Levenshtein as L
@dataclass
class Edit:
    start: int; end: int; replacement: str; confidence: float | None = None; source: str = ''
@dataclass
class Correction:
    line_id: str; source_text: str; edits: list = field(default_factory=list)
    @property
    def corrected_text(self): return applique(self.source_text, self.edits)
def applique(src, edits):
    out, pos = [], 0
    for e in sorted(edits, key=lambda e: (e.start, e.end)):
        assert pos <= e.start <= e.end <= len(src), 'éditions chevauchantes ou hors ligne'
        out.append(src[pos:e.start]); out.append(e.replacement); pos = e.end
    out.append(src[pos:]); return ''.join(out)
def editions(src, tgt, source=''):
    """éditions minimales src → tgt (réalignement, pour les systèmes génératifs) ; blocs contigus fusionnés"""
    ed = []
    for op in L.opcodes(src, tgt):
        if op.tag == 'equal': continue
        e = Edit(op.src_start, op.src_end, tgt[op.dest_start:op.dest_end], None, source)
        if ed and ed[-1].end == e.start: ed[-1] = Edit(ed[-1].start, e.end, ed[-1].replacement + e.replacement, None, source)
        else: ed.append(e)
    return ed
