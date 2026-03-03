from __future__ import annotations

from pylatexenc.latex2text import LatexNodes2Text
import unicodeit


# Module-level converter instance (stateless, reusable, thread-safe)
_L2T = LatexNodes2Text()


def latexToUnicode(latex: str) -> str:
    """Convert a LaTeX math expression to Unicode text.

    Uses pylatexenc for macro expansion (\\alpha -> α, \\frac{a}{b} -> a/b),
    then unicodeit for superscript/subscript conversion (^2 -> ², _i -> ᵢ).
    """
    # pylatexenc converts macros to Unicode
    text = _L2T.latex_to_text(latex)
    # unicodeit converts super/subscripts to Unicode chars
    try:
        text = unicodeit.replace(text)
    except Exception:
        pass  # unicodeit can fail on edge cases; pylatexenc output is fine
    return text
