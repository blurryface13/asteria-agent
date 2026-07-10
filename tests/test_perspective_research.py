import unittest
from unittest.mock import AsyncMock, patch

from multi_agents.agents.researcher import ResearchAgent


class PerspectiveResearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_perspectives_bounds_and_normalizes_model_output(self):
        agent = ResearchAgent()
        response = {
            "perspectives": [
                {"role": "theorist", "focus": "math", "questions": ["q1", "q2", "q3"]},
                {"role": "engineer", "focus": "implementation", "questions": ["q4"]},
                {"role": "duplicate", "focus": "extra", "questions": []},
            ]
        }
        with patch("multi_agents.agents.researcher.call_model", new=AsyncMock(return_value=response)):
            perspectives = await agent.generate_perspectives(
                "SLAM", "classic algorithms", "test-model", max_perspectives=2, questions_per_perspective=2
            )

        self.assertEqual(len(perspectives), 2)
        self.assertEqual(perspectives[0]["questions"], ["q1", "q2"])
        self.assertEqual(perspectives[1]["role"], "engineer")

    async def test_perspective_reports_are_synthesized_back_to_one_section(self):
        agent = ResearchAgent()
        agent.generate_perspectives = AsyncMock(return_value=[
            {"role": "theorist", "focus": "math", "questions": ["q1"]},
            {"role": "engineer", "focus": "implementation", "questions": ["q2"]},
        ])
        agent._run_perspective_research = AsyncMock(side_effect=[
            {"role": "theorist", "focus": "math", "report": "theory evidence"},
            {"role": "engineer", "focus": "implementation", "report": "engineering evidence"},
        ])
        agent._synthesize_perspective_reports = AsyncMock(return_value="merged section")

        result = await agent.run_perspective_research(
            parent_query="SLAM learning roadmap",
            subtopic="classic SLAM algorithms",
            task={"model": "test-model", "max_perspectives": 2, "questions_per_perspective": 2},
        )

        self.assertEqual(result, {"classic SLAM algorithms": "merged section"})
        agent._synthesize_perspective_reports.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
