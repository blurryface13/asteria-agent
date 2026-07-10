import asyncio

from asteria_researcher import AsteriaResearcher
from colorama import Fore, Style
from .utils.views import print_agent_output
from .utils.llms import call_model


PERSPECTIVE_SYSTEM_PROMPT = """You are a research strategist. Given one report
section, identify complementary perspectives that will improve evidence coverage.
Each perspective must represent a distinct research need, not a writing style."""


class ResearchAgent:
    def __init__(self, websocket=None, stream_output=None, tone=None, headers=None):
        self.websocket = websocket
        self.stream_output = stream_output
        self.headers = headers or {}
        self.tone = tone
        self._perspective_semaphore = None
        self._perspective_concurrency = None

    async def research(self, query: str, research_report: str = "research_report",
                       parent_query: str = "", verbose=True, source="web", tone=None, headers=None):
        request_headers = dict(self.headers)
        if headers:
            request_headers.update(headers)
        # Initialize the researcher
        researcher = AsteriaResearcher(query=query, report_type=research_report, parent_query=parent_query,
                                   verbose=verbose, report_source=source, tone=tone, websocket=self.websocket, headers=request_headers)
        # Conduct research on the given query
        await researcher.conduct_research()
        # Write the report
        report = await researcher.write_report()

        return report

    async def run_subtopic_research(self, parent_query: str, subtopic: str, verbose: bool = True, source="web", headers=None):
        try:
            report = await self.research(parent_query=parent_query, query=subtopic,
                                         research_report="subtopic_report", verbose=verbose, source=source, tone=self.tone, headers=headers)
        except Exception as e:
            print(f"{Fore.RED}Error in researching topic {subtopic}: {e}{Style.RESET_ALL}")
            report = None
        return {subtopic: report}

    async def generate_perspectives(
        self,
        parent_query: str,
        section: str,
        model: str,
        max_perspectives: int,
        questions_per_perspective: int,
    ) -> list[dict[str, object]]:
        """Create bounded, section-specific viewpoints for STORM-style research."""
        prompt = [
            {"role": "system", "content": PERSPECTIVE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""Main research topic: {parent_query}
Section to investigate: {section}

Return JSON only in this shape:
{{"perspectives": [
  {{"role": "short domain role", "focus": "distinct evidence focus", "questions": ["question 1", "question 2"]}}
]}}

Return at most {max_perspectives} perspectives and at most {questions_per_perspective}
questions per perspective. Avoid generic roles and avoid duplicate coverage.""",
            },
        ]
        try:
            response = await call_model(prompt, model=model, response_format="json")
        except Exception as error:
            print(f"{Fore.YELLOW}Perspective planning failed: {error}{Style.RESET_ALL}")
            return []

        if not isinstance(response, dict):
            return []

        perspectives: list[dict[str, object]] = []
        for item in response.get("perspectives", []):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            focus = str(item.get("focus") or "").strip()
            raw_questions = item.get("questions", [])
            if not isinstance(raw_questions, list):
                raw_questions = []
            questions = [
                str(question).strip()
                for question in raw_questions
                if str(question).strip()
            ][:questions_per_perspective]
            if role and focus:
                perspectives.append({"role": role, "focus": focus, "questions": questions})
            if len(perspectives) >= max_perspectives:
                break
        return perspectives

    async def _run_perspective_research(
        self,
        parent_query: str,
        section: str,
        perspective: dict[str, object],
        verbose: bool,
        source: str,
        headers: dict | None,
    ) -> dict[str, str] | None:
        role = str(perspective["role"])
        focus = str(perspective["focus"])
        questions = perspective.get("questions", [])
        question_text = "\n".join(f"- {question}" for question in questions)
        perspective_query = f"""{section}

Research from the perspective of a {role}.
Focus: {focus}
Questions to resolve:
{question_text or '- Identify the evidence most relevant to this perspective.'}
Preserve trustworthy source links for every substantive claim."""
        try:
            report = await self.research(
                parent_query=parent_query,
                query=perspective_query,
                research_report="subtopic_report",
                verbose=verbose,
                source=source,
                tone=self.tone,
                headers=headers,
            )
            return {"role": role, "focus": focus, "report": report}
        except Exception as error:
            print(f"{Fore.RED}Perspective research failed for {role}: {error}{Style.RESET_ALL}")
            return None

    async def _synthesize_perspective_reports(
        self,
        section: str,
        perspective_reports: list[dict[str, str]],
        model: str,
    ) -> str:
        """Return one section report so downstream writer/publisher contracts stay unchanged."""
        evidence = "\n\n".join(
            f"Perspective: {item['role']}\nFocus: {item['focus']}\nFindings:\n{item['report'][:8000]}"
            for item in perspective_reports
        )
        prompt = [
            {
                "role": "system",
                "content": "You are a research editor who synthesizes evidence into a single grounded report section.",
            },
            {
                "role": "user",
                "content": f"""Write the section '{section}' from the perspective reports below.
Merge complementary findings, remove repetition, and preserve source hyperlinks from the evidence.
Do not invent claims or citations. Return Markdown only.

{evidence}""",
            },
        ]
        try:
            response = await call_model(prompt, model=model)
            if isinstance(response, str) and response.strip():
                return response
        except Exception as error:
            print(f"{Fore.YELLOW}Perspective synthesis failed: {error}{Style.RESET_ALL}")
        return "\n\n".join(item["report"] for item in perspective_reports)

    async def run_perspective_research(
        self,
        parent_query: str,
        subtopic: str,
        task: dict,
        verbose: bool = True,
        source: str = "web",
        headers: dict | None = None,
    ) -> dict[str, str | None]:
        max_perspectives = max(1, min(int(task.get("max_perspectives", 2)), 4))
        questions_per_perspective = max(1, min(int(task.get("questions_per_perspective", 2)), 3))
        max_parallel = max(1, min(int(task.get("max_parallel_perspective_research", 2)), 4))
        timeout_s = max(60, min(int(task.get("perspective_research_timeout_s", 360)), 900))
        if self._perspective_semaphore is None or self._perspective_concurrency != max_parallel:
            self._perspective_semaphore = asyncio.Semaphore(max_parallel)
            self._perspective_concurrency = max_parallel
        perspectives = await self.generate_perspectives(
            parent_query,
            subtopic,
            task.get("model"),
            max_perspectives,
            questions_per_perspective,
        )
        if not perspectives:
            return await self.run_subtopic_research(parent_query, subtopic, verbose, source, headers)

        if self.websocket and self.stream_output:
            await self.stream_output(
                "logs",
                "perspective_plan",
                f"Generated {len(perspectives)} research perspectives for: {subtopic}",
                self.websocket,
            )
        else:
            print_agent_output(f"Researching {subtopic} from {len(perspectives)} perspectives...", agent="RESEARCHER")

        async def run_limited(perspective):
            async with self._perspective_semaphore:
                try:
                    return await asyncio.wait_for(
                        self._run_perspective_research(
                            parent_query, subtopic, perspective, verbose, source, headers
                        ),
                        timeout=timeout_s,
                    )
                except asyncio.TimeoutError:
                    role = str(perspective.get("role", "unknown perspective"))
                    print(f"{Fore.YELLOW}Perspective research timed out for {role}{Style.RESET_ALL}")
                    return None

        results = await asyncio.gather(
            *[
                run_limited(perspective)
                for perspective in perspectives
            ]
        )
        reports = [result for result in results if result and result.get("report")]
        if not reports:
            return {subtopic: None}
        return {
            subtopic: await self._synthesize_perspective_reports(
                subtopic, reports, task.get("model")
            )
        }

    async def run_initial_research(self, research_state: dict):
        task = research_state.get("task")
        query = task.get("query")
        source = task.get("source", "web")
        headers = dict(task.get("headers") or {})
        if task.get("retrievers") and not headers.get("retrievers"):
            headers["retrievers"] = task.get("retrievers")

        if self.websocket and self.stream_output:
            await self.stream_output("logs", "initial_research", f"Running initial research on the following query: {query}", self.websocket)
        else:
            print_agent_output(f"Running initial research on the following query: {query}", agent="RESEARCHER")
        return {"task": task, "initial_research": await self.research(query=query, verbose=task.get("verbose"),
                                                                      source=source, tone=self.tone, headers=headers)}

    async def run_depth_research(self, draft_state: dict):
        task = draft_state.get("task")
        topic = draft_state.get("topic")
        parent_query = task.get("query")
        source = task.get("source", "web")
        verbose = task.get("verbose")
        headers = dict(task.get("headers") or {})
        if task.get("retrievers") and not headers.get("retrievers"):
            headers["retrievers"] = task.get("retrievers")
        if self.websocket and self.stream_output:
            await self.stream_output("logs", "depth_research", f"Running in depth research on the following report topic: {topic}", self.websocket)
        else:
            print_agent_output(f"Running in depth research on the following report topic: {topic}", agent="RESEARCHER")
        if task.get("perspective_guided_research", False):
            research_draft = await self.run_perspective_research(
                parent_query=parent_query,
                subtopic=topic,
                task=task,
                verbose=verbose,
                source=source,
                headers=headers,
            )
        else:
            research_draft = await self.run_subtopic_research(
                parent_query=parent_query,
                subtopic=topic,
                verbose=verbose,
                source=source,
                headers=headers,
            )
        return {"draft": research_draft}
