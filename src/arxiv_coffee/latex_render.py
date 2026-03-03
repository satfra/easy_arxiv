from __future__ import annotations

import io

from PIL import Image


def renderLatexToImage(
    latex: str,
    *,
    dpi: int = 150,
    color: str = "white",
) -> Image.Image:
    """Render a LaTeX math expression to a PIL Image in memory.

    Uses matplotlib's built-in mathtext parser with the Agg backend.
    No system TeX installation required.
    """
    import matplotlib

    matplotlib.use("agg")
    from matplotlib.mathtext import math_to_image

    buf = io.BytesIO()
    math_to_image(f"${latex}$", buf, dpi=dpi, format="png", color=color)
    buf.seek(0)
    return Image.open(buf)
