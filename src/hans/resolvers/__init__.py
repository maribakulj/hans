"""Resolvers: given a box and tokens, say where each token sits."""

from hans.resolvers.ctc import CTCCutsResolver
from hans.resolvers.proportional import ProportionalResolver

__all__ = ["CTCCutsResolver", "ProportionalResolver"]
