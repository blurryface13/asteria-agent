"""Scraper implementations with lazy imports.

The scraper package contains optional integrations with PDF loaders, browser
automation, and third-party extraction services. Importing all of them during
application startup makes a normal web research task pay the dependency cost
of every unused integration (including spaCy through LangChain's PDF stack).
Keep the public names compatible while loading an implementation only when it
is requested.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .arxiv.arxiv import ArxivScraper
    from .beautiful_soup.beautiful_soup import BeautifulSoupScraper
    from .browser.browser import BrowserScraper
    from .browser.nodriver_scraper import NoDriverScraper
    from .firecrawl.firecrawl import FireCrawl
    from .pymupdf.pymupdf import PyMuPDFScraper
    from .scraper import Scraper
    from .tavily_extract.tavily_extract import TavilyExtract
    from .web_base_loader.web_base_loader import WebBaseLoaderScraper


_LAZY_IMPORTS = {
    "BeautifulSoupScraper": ".beautiful_soup.beautiful_soup",
    "WebBaseLoaderScraper": ".web_base_loader.web_base_loader",
    "ArxivScraper": ".arxiv.arxiv",
    "PyMuPDFScraper": ".pymupdf.pymupdf",
    "BrowserScraper": ".browser.browser",
    "NoDriverScraper": ".browser.nodriver_scraper",
    "TavilyExtract": ".tavily_extract.tavily_extract",
    "FireCrawl": ".firecrawl.firecrawl",
    "Scraper": ".scraper",
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
    "BeautifulSoupScraper",
    "WebBaseLoaderScraper",
    "ArxivScraper",
    "PyMuPDFScraper",
    "BrowserScraper",
    "NoDriverScraper",
    "TavilyExtract",
    "Scraper",
    "FireCrawl",
]
