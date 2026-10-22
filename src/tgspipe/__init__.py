"""tgspipe — a production pipeline for Telegram .tgs animated emoji/stickers.

Stages: build (character rigs) -> validate (hard spec gates) -> optimize
(size budget) -> render (preview frames) -> qa (loop seam + frame diff).

The core is dependency-free (stdlib only). Rendering previews to PNG
needs Pillow (the ``render`` extra).
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
