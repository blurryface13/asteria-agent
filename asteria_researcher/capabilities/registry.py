"""Registry for composing task-specific Skills, Agents, and Tools."""

from __future__ import annotations

from collections.abc import Iterable

from .models import AgentProfile, SkillManifest, TaskIntent, ToolSpec


class CapabilityRegistry:
    """In-memory registry; persistence can be added without changing contracts."""

    def __init__(self) -> None:
        self.skills: dict[str, SkillManifest] = {}
        self.agents: dict[str, AgentProfile] = {}
        self.tools: dict[str, ToolSpec] = {}

    def register_skill(self, manifest: SkillManifest) -> SkillManifest:
        self._register(self.skills, manifest.id, manifest, "skill")
        return manifest

    def register_agent(self, profile: AgentProfile) -> AgentProfile:
        self._register(self.agents, profile.id, profile, "agent")
        return profile

    def register_tool(self, tool: ToolSpec) -> ToolSpec:
        self._register(self.tools, tool.id, tool, "tool")
        return tool

    def get_skill(self, skill_id: str) -> SkillManifest:
        try:
            return self.skills[skill_id]
        except KeyError as error:
            raise KeyError(f"unknown skill: {skill_id}") from error

    def get_agent(self, agent_id: str) -> AgentProfile:
        try:
            return self.agents[agent_id]
        except KeyError as error:
            raise KeyError(f"unknown agent: {agent_id}") from error

    def get_tool(self, tool_id: str) -> ToolSpec:
        try:
            return self.tools[tool_id]
        except KeyError as error:
            raise KeyError(f"unknown tool: {tool_id}") from error

    def resolve_skills(self, intent: str, requested: Iterable[str] = ()) -> list[SkillManifest]:
        """Resolve intent defaults plus explicit internal additions, preserving order."""

        requested_ids = list(requested)
        candidates = [
            manifest
            for manifest in self.skills.values()
            if intent in manifest.intents and manifest.status != "planned"
        ]
        by_id = {manifest.id: manifest for manifest in candidates}
        resolved: list[SkillManifest] = []
        resolved_ids: set[str] = set()
        for skill_id in [manifest.id for manifest in candidates] + requested_ids:
            manifest = by_id.get(skill_id) or self.skills.get(skill_id)
            if manifest is not None and manifest.status != "planned" and manifest.id not in resolved_ids:
                resolved.append(manifest)
                resolved_ids.add(manifest.id)
        return resolved

    @staticmethod
    def _register(target: dict, identifier: str, value: object, kind: str) -> None:
        if identifier in target:
            raise ValueError(f"duplicate {kind} id: {identifier}")
        target[identifier] = value


def build_default_registry() -> CapabilityRegistry:
    """Register the current research path and planned extension points."""

    registry = CapabilityRegistry()

    registry.register_tool(ToolSpec(
        id="web_search",
        name="Web Search",
        description="Search public web sources for research evidence.",
        transport="in_process",
        permission="network",
        timeout_seconds=120,
    ))
    registry.register_tool(ToolSpec(
        id="mcp_research",
        name="MCP Research",
        description="Query configured MCP servers and normalize evidence items.",
        transport="mcp",
        permission="network",
        timeout_seconds=300,
    ))
    registry.register_tool(ToolSpec(
        id="workspace_artifact",
        name="Workspace Artifact",
        description="Read or write task-scoped notes and report artifacts.",
        transport="in_process",
        permission="write",
        timeout_seconds=60,
    ))
    registry.register_tool(ToolSpec(
        id="report_structure_check",
        name="Report Structure Check",
        description="Check report headings and language-facing delivery structure.",
        transport="in_process",
        permission="read",
        input_schema={"type": "object", "required": ["markdown"],
                      "properties": {"markdown": {"type": "string"},
                                     "target_chars": {"type": ["integer", "null"]}}},
        output_schema={"type": "object", "required": ["ok", "issues", "headings"]},
        timeout_seconds=30,
    ))
    registry.register_tool(ToolSpec(
        id="citation_audit",
        name="Citation Audit",
        description="Match report citations to sources actually read in the current task.",
        transport="in_process",
        permission="read",
        input_schema={"type": "object", "required": ["markdown", "allowed_urls"],
                      "properties": {"markdown": {"type": "string"},
                                     "allowed_urls": {"type": "array", "items": {"type": "string"}}}},
        output_schema={"type": "object", "required": ["ok", "citation_urls", "invalid_urls"]},
        timeout_seconds=60,
    ))
    registry.register_tool(ToolSpec(
        id="latex_compile",
        name="LaTeX Compile",
        description="Publish Markdown using an independent trusted format profile; archive TeX, PDF and compiler output.",
        transport="in_process",
        permission="write",
        input_schema={"type": "object", "required": ["markdown"],
                      "properties": {"markdown": {"type": "string"},
                                     "profile": {"type": "string", "enum": ["academic", "brief"]}}},
        output_schema={"type": "object", "required": ["tex", "latex_pdf", "compile_log", "md"]},
        timeout_seconds=120,
    ))

    registry.register_tool(ToolSpec(
        id="bibliography_resolver",
        name="Bibliography Resolver",
        description="Catalog description of runtime references(paper_ids=[read URL], query): resolve literal bibliography entries. Not a separate action.",
        transport="in_process",
        permission="network",
        input_schema={"type": "object", "required": ["paper_ids", "query"],
                      "properties": {"paper_ids": {"type": "array", "minItems": 1, "maxItems": 1, "items": {"type": "string"}},
                                     "query": {"type": "string"}}},
        output_schema={"type": "object", "required": ["resolved", "unresolved"]},
        timeout_seconds=300,
    ))
    registry.register_tool(ToolSpec(
        id="citation_graph",
        name="Citation Graph",
        description="Runtime-owned PaperLibrary snapshot/save, not an LLM action. Nodes and edges come only from verified tool results.",
        transport="in_process",
        permission="write",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={"type": "object", "required": ["nodes", "edges", "unresolved_references"]},
        timeout_seconds=60,
    ))

    registry.register_agent(AgentProfile(
        id="editor",
        name="Research Editor",
        role="planner",
        implementation="multi_agents.agents.editor.EditorAgent",
        description="Plan report sections and coordinate section research.",
        allowed_tools=["web_search", "mcp_research", "bibliography_resolver", "citation_graph"],
        allowed_skills=["literature_search", "survey_writing"],
        can_delegate=True,
        status="active",
    ))
    registry.register_agent(AgentProfile(
        id="researcher",
        name="Researcher",
        role="evidence_collector",
        implementation="multi_agents.agents.researcher.ResearchAgent",
        description="Search, read, and organize evidence for a research section.",
        allowed_tools=["web_search", "mcp_research", "bibliography_resolver", "citation_graph", "workspace_artifact"],
        allowed_skills=["literature_search", "evidence_extraction"],
        can_delegate=False,
        status="active",
    ))
    registry.register_agent(AgentProfile(
        id="writer",
        name="Report Writer",
        role="writer",
        implementation="multi_agents.agents.writer.WriterAgent",
        description="Turn reviewed research data into a structured report.",
        allowed_tools=["workspace_artifact"],
        allowed_skills=["survey_writing"],
        status="active",
    ))
    registry.register_agent(AgentProfile(
        id="evidence_checker",
        name="Evidence Checker",
        role="verifier",
        implementation="multi_agents.agents.fact_checker.FactCheckerAgent",
        description="Check factual consistency before report delivery.",
        allowed_tools=["workspace_artifact"],
        allowed_skills=["citation_verification", "evidence_extraction"],
        status="partial",
    ))

    registry.register_skill(SkillManifest(
        id="academic_research",
        name="Academic Research",
        description="Current end-to-end academic research workflow.",
        implementation="multi_agents.agents.orchestrator.ChiefEditorAgent",
        intents=[TaskIntent.ACADEMIC_RESEARCH.value],
        capabilities=["task_planning", "parallel_research", "report_writing"],
        allowed_agents=["editor", "researcher", "writer", "evidence_checker"],
        allowed_tools=["web_search", "mcp_research", "bibliography_resolver", "citation_graph", "workspace_artifact"],
        validators=["outline_check", "citation_check"],
        status="active",
    ))
    registry.register_skill(SkillManifest(
        id="literature_search",
        name="Literature Search",
        description="Search and collect academic sources; current implementation is embedded in ResearchAgent.",
        implementation="asteria_researcher.skills.researcher.ResearchConductor",
        intents=[TaskIntent.ACADEMIC_RESEARCH.value],
        capabilities=["query_decomposition", "source_retrieval", "mcp_routing"],
        allowed_agents=["editor", "researcher"],
        allowed_tools=["web_search", "mcp_research", "bibliography_resolver", "citation_graph"],
        status="partial",
    ))
    registry.register_skill(SkillManifest(
        id="evidence_extraction",
        name="Evidence Extraction",
        description="Extract research evidence into a normalized structure for downstream verification.",
        implementation="asteria_researcher.skills.researcher.ResearchConductor",
        intents=[TaskIntent.ACADEMIC_RESEARCH.value],
        capabilities=["context_processing", "source_normalization"],
        allowed_agents=["researcher", "evidence_checker"],
        allowed_tools=["workspace_artifact"],
        status="partial",
    ))
    registry.register_skill(SkillManifest(
        id="citation_verification",
        name="Citation Verification",
        description="Verify factual consistency and source support before delivery.",
        implementation="multi_agents.agents.fact_checker.FactCheckerAgent",
        intents=[TaskIntent.ACADEMIC_RESEARCH.value],
        capabilities=["fact_checking", "citation_check"],
        allowed_agents=["evidence_checker"],
        allowed_tools=["workspace_artifact"],
        status="partial",
    ))
    registry.register_skill(SkillManifest(
        id="survey_writing",
        name="Survey Writing",
        description="Generate structured research reports from collected evidence.",
        implementation="multi_agents.agents.writer.WriterAgent",
        intents=[TaskIntent.ACADEMIC_RESEARCH.value],
        capabilities=["outline_generation", "report_writing"],
        allowed_agents=["writer"],
        allowed_tools=["workspace_artifact", "report_structure_check", "citation_audit", "latex_compile"],
        validators=["outline_check", "citation_audit", "latex_compile"],
        status="active",
    ))
    # Runtime content/format skills share one catalog; metadata is not a tool grant.
    from asteria_researcher.agentic.skill_catalog import catalog
    for phase in ("writing", "formatting"):
        for entry in catalog(phase):
            if entry["id"] in registry.skills:
                continue
            registry.register_skill(SkillManifest(
                id=entry["id"], name=entry["id"].replace("_", " ").title(),
                version=entry["version"], description=entry["description"],
                implementation="asteria_researcher.agentic.skill_catalog",
                intents=[intent.value for intent in TaskIntent],
                capabilities=[phase], allowed_agents=["writer"],
                allowed_tools=[], validators=["citation_audit"], status="active",
            ))

    registry.register_skill(SkillManifest(
        id="experiment_execution",
        name="Experiment Execution",
        description="Run a versioned experiment recipe inside a user-authorized host and workspace.",
        implementation="planned.experiment_worker",
        intents=[TaskIntent.EXPERIMENT.value],
        capabilities=["recipe_execution", "metric_collection", "artifact_archiving"],
        status="planned",
    ))
    registry.register_skill(SkillManifest(
        id="offline_rag_qa",
        name="Offline RAG QA",
        description="Answer questions from an explicitly selected local knowledge base.",
        implementation="backend.knowledge.modular_rag",
        intents=[TaskIntent.OFFLINE_RAG.value],
        capabilities=["hybrid_retrieval", "grounded_answering"],
        status="partial",
    ))
    registry.register_skill(SkillManifest(
        id="data_analysis",
        name="Data Analysis",
        description="Analyze user-authorized data and produce reproducible metrics and figures.",
        implementation="planned.data_analysis_agent",
        intents=[TaskIntent.DATA_ANALYSIS.value],
        capabilities=["dataset_inspection", "python_execution", "visualization"],
        status="planned",
    ))

    return registry
