import hashlib
import time
from fastapi import WebSocket
from typing import Any

from asteria_researcher import AsteriaResearcher


class BasicReport:
    def __init__(
        self,
        query: str,
        query_domains: list,
        report_type: str,
        report_source: str,
        source_urls,
        document_urls,
        tone: Any,
        config_path: str,
        websocket: WebSocket,
        headers=None,
        mcp_configs=None,
        mcp_strategy=None,
        max_search_results=None,
    ):
        self.query = query
        self.query_domains = query_domains
        self.report_type = report_type
        self.report_source = report_source
        self.source_urls = source_urls
        self.document_urls = document_urls
        self.tone = tone
        self.config_path = config_path
        self.websocket = websocket
        self.headers = headers or {}
        
        # Generate a unique research ID for this report
        self.research_id = self._generate_research_id(query)

        # Initialize researcher with optional MCP parameters
        asteria_researcher_params = {
            "query": self.query,
            "query_domains": self.query_domains,
            "report_type": self.report_type,
            "report_source": self.report_source,
            "source_urls": self.source_urls,
            "document_urls": self.document_urls,
            "tone": self.tone,
            "config_path": self.config_path,
            "websocket": self.websocket,
            "headers": self.headers,
        }

        # Add MCP parameters if provided
        if mcp_configs is not None:
            asteria_researcher_params["mcp_configs"] = mcp_configs
        if mcp_strategy is not None:
            asteria_researcher_params["mcp_strategy"] = mcp_strategy

        self.asteria_researcher = AsteriaResearcher(**asteria_researcher_params)

        # Override max_search_results_per_query if provided by user
        if max_search_results is not None:
            self.asteria_researcher.cfg.max_search_results_per_query = int(max_search_results)

    def _generate_research_id(self, query: str) -> str:
        """Generate a unique research ID from query and timestamp."""
        timestamp = str(int(time.time()))
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        return f"research_{timestamp}_{query_hash}"

    async def run(self):
        await self.asteria_researcher.conduct_research()
        report = await self.asteria_researcher.write_report()
        return report
