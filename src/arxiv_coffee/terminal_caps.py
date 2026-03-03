from __future__ import annotations

# Flags set at import time.
HAS_GRAPHICS: bool = False
HAS_MATH_IMAGE: bool = False

try:
    # Importing textual_image.renderable triggers terminal probing.
    # This MUST happen before ArxivCoffeApp.run().
    from textual_image.renderable import Image as _AutoRenderable
    from textual_image.renderable.halfcell import Image as _HalfcellRenderable
    from textual_image.renderable.unicode import Image as _UnicodeRenderable

    HAS_GRAPHICS = _AutoRenderable not in (_HalfcellRenderable, _UnicodeRenderable)

    # Also trigger cell size cache (textual-image needs this before Textual starts)
    from textual_image.widget import Image as _WidgetImage  # noqa: F401

    import matplotlib  # noqa: F401

    HAS_MATH_IMAGE = True
except ImportError:
    pass
