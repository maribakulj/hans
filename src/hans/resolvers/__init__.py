"""Resolvers: given a box and tokens, say where each token sits."""

from hans.resolvers.ctc import CTCCutsResolver, WeightedCTCCutsResolver
from hans.resolvers.inkgap import InkGapResolver
from hans.resolvers.inksnap import InkSnapResolver
from hans.resolvers.proportional import ProportionalResolver
from hans.resolvers.tesseract import TesseractWordsResolver

__all__ = [
    "CTCCutsResolver",
    "InkGapResolver",
    "InkSnapResolver",
    "ProportionalResolver",
    "TesseractWordsResolver",
    "WeightedCTCCutsResolver",
]
