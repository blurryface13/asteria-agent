"""Research skills with lazy public exports.

Skills depend on different optional stacks (web scraping, document loading,
image generation, and context compression). Importing every skill whenever a
single skill is requested creates a large and fragile startup dependency graph.
The public names remain unchanged and are resolved on first use.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .browser import BrowserManager
    from .context_manager import ContextManager
    from .curator import SourceCurator
    from .image_generator import ImageGenerator
    from .researcher import ResearchConductor
    from .writer import ReportGenerator


_LAZY_IMPORTS = {
    "ContextManager": ".context_manager",
    "ResearchConductor": ".researcher",
    "ReportGenerator": ".writer",
    "BrowserManager": ".browser",
    "SourceCurator": ".curator",
    "ImageGenerator": ".image_generator",
}


def __getattr__(name: str):
    module_name = _LAZY_IMPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value

__all__ = [
    'ResearchConductor',
    'ReportGenerator',
    'ContextManager',
    'BrowserManager',
    'SourceCurator',
    'ImageGenerator',
]
