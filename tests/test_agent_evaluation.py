import unittest

from multi_agents.evaluation import cited_claims, count_citations, outline_coverage


class AgentEvaluationTests(unittest.TestCase):
    def test_outline_coverage_matches_semantically_similar_headings(self):
        report = """# Report
## Mathematical foundations
## Classical SLAM algorithms
## Practical implementation resources
"""
        score = outline_coverage(
            report,
            ["mathematical foundations", "classic SLAM algorithms", "implementation practice and learning resources"],
        )
        self.assertGreaterEqual(score, 2 / 3)

    def test_cited_claim_helpers_extract_unique_links(self):
        report = "A grounded claim ([source](https://example.com/a)). Another ([same](https://example.com/a))."
        self.assertEqual(count_citations(report), 1)
        self.assertEqual(len(cited_claims(report)), 2)


if __name__ == "__main__":
    unittest.main()
