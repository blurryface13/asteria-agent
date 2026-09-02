"""Retriever implementations with lazy imports.

Each retriever may bring its own optional SDK or network integration. Keep the
same public exports as before, but load only the retriever selected by the
current configuration instead of importing every integration at startup.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .arxiv.arxiv import ArxivSearch
    from .bing.bing import BingSearch
    from .bocha.bocha import BoChaSearch
    from .brave.brave import BraveSearch
    from .crw.crw import CRWRetriever
    from .custom.custom import CustomRetriever
    from .duckduckgo.duckduckgo import Duckduckgo
    from .exa.exa import ExaSearch
    from .google.google import GoogleSearch
    from .groundroute.groundroute import GroundRouteSearch
    from .mcp import MCPRetriever
    from .openalex.openalex import OpenAlexSearch
    from .pubmed_central.pubmed_central import PubMedCentralSearch
    from .searchapi.searchapi import SearchApiSearch
    from .searx.searx import SearxSearch
    from .semantic_scholar.semantic_scholar import SemanticScholarSearch
    from .serpapi.serpapi import SerpApiSearch
    from .serper.serper import SerperSearch
    from .tavily.tavily_search import TavilySearch
    from .xquik.xquik import XquikSearch


_LAZY_IMPORTS = {
    "ArxivSearch": ".arxiv.arxiv",
    "BingSearch": ".bing.bing",
    "BoChaSearch": ".bocha.bocha",
    "BraveSearch": ".brave.brave",
    "CRWRetriever": ".crw.crw",
    "CustomRetriever": ".custom.custom",
    "Duckduckgo": ".duckduckgo.duckduckgo",
    "ExaSearch": ".exa.exa",
    "GoogleSearch": ".google.google",
    "GroundRouteSearch": ".groundroute.groundroute",
    "MCPRetriever": ".mcp.retriever",
    "OpenAlexSearch": ".openalex.openalex",
    "PubMedCentralSearch": ".pubmed_central.pubmed_central",
    "SearchApiSearch": ".searchapi.searchapi",
    "SearxSearch": ".searx.searx",
    "SemanticScholarSearch": ".semantic_scholar.semantic_scholar",
    "SerpApiSearch": ".serpapi.serpapi",
    "SerperSearch": ".serper.serper",
    "TavilySearch": ".tavily.tavily_search",
    "XquikSearch": ".xquik.xquik",
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
    "TavilySearch",
    "GroundRouteSearch",
    "CustomRetriever",
    "Duckduckgo",
    "SearchApiSearch",
    "SerperSearch",
    "SerpApiSearch",
    "GoogleSearch",
    "SearxSearch",
    "BingSearch",
    "BraveSearch",
    "ArxivSearch",
    "SemanticScholarSearch",
    "PubMedCentralSearch",
    "ExaSearch",
    "CRWRetriever",
    "MCPRetriever",
    "BoChaSearch",
    "XquikSearch",
    "OpenAlexSearch"
]
