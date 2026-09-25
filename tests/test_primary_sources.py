import pytest
import asyncio
import httpx
import urllib.error
from asteria_researcher.agentic.primary_sources import (
    validate_url, source_type, paper_url, extract_text, explicit_arxiv_urls,
)


@pytest.mark.parametrize("url", ["http://arxiv.org/abs/1706.03762", "https://127.0.0.1/x",
    "https://arxiv.org.evil.example/a", "https://user@arxiv.org/a", "https://arxiv.org:444/a",
    "https://anthropic.com.evil.example/a", "http://openai.com/a", "https://user@x.ai/a",
    "https://data.x.ai:444/a"])
def test_reject_untrusted_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_full_paper_representation():
    assert paper_url("https://arxiv.org/abs/1706.03762") == "https://arxiv.org/pdf/1706.03762"


@pytest.mark.parametrize(("url", "kind"), [
    ("https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents", "institutional_report"),
    ("https://cdn.openai.com/pdf/report.pdf", "institutional_report"),
    ("https://data.x.ai/model-card.pdf", "institutional_report"),
    ("https://arxiv.org/abs/1706.03762", "academic_preprint"),
    ("https://aclanthology.org/2025.acl-long.1/", "academic_publication"),
])
def test_research_sources_have_explicit_type(url, kind):
    assert validate_url(url) == url
    assert source_type(url) == kind


def test_only_explicit_arxiv_identifiers_become_paper_seeds():
    assert explicit_arxiv_urls("阅读 arXiv:1706.03762 和 arxiv:1810.04805v2") == {
        "https://arxiv.org/abs/1706.03762", "https://arxiv.org/abs/1810.04805v2"}
    assert explicit_arxiv_urls("编号 1706.03762；不要猜测论文身份") == set()


def test_html_extraction():
    assert extract_text(b"<p>Evidence</p><script>bad()</script>", "text/html") == "Evidence"


def test_html_extraction_prefers_article_content_over_site_chrome(tmp_path):
    from asteria_researcher.agentic.primary_sources import extract_file
    path = tmp_path / "report.html"
    path.write_bytes(b"<html><header>Site navigation</header><article><h1>Research</h1>"
                     b"<p>Primary evidence</p></article><footer>Legal</footer></html>")
    text, pages = extract_file(path, "text/html")
    assert "Research" in text and "Primary evidence" in text
    assert "Site navigation" not in text and "Legal" not in text
    assert pages[0]["page"] == 1


def test_pdf_extraction():
    import fitz
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 30), "Primary evidence")
        result = extract_text(doc.tobytes(), "application/pdf")
    assert "[Page 1]" in result and "Primary evidence" in result


def test_search_returns_real_records(monkeypatch):
    from asteria_researcher.agentic import primary_sources
    monkeypatch.setenv("REVIEW_ARXIV_SEARCH_PROVIDER", "atom")
    original_client = httpx.AsyncClient

    def respond(request):
        assert request.url.params["search_query"] == 'ti:"Attention Is All You Need"'
        assert request.url.params["max_results"] == "15"
        return httpx.Response(200, content=b'''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>Attention Is All You Need</title>
          <id>http://arxiv.org/abs/1706.03762v7</id><summary>Original abstract.</summary></entry>
        </feed>''')

    monkeypatch.setattr(primary_sources.httpx, "AsyncClient", lambda **kwargs:
                        original_client(transport=httpx.MockTransport(respond)))
    records = asyncio.run(primary_sources.search_papers('ti:"Attention Is All You Need"'))
    assert records == [{"title": "Attention Is All You Need",
                        "url": "https://arxiv.org/abs/1706.03762v7", "abstract": "Original abstract.",
                        "published": "", "updated": ""}]


def test_search_uses_bounded_urllib_fallback_only_for_transport_406(monkeypatch):
    from asteria_researcher.agentic import primary_sources
    monkeypatch.setenv("REVIEW_ARXIV_SEARCH_PROVIDER", "atom")
    monkeypatch.setattr(primary_sources, "_atom_unavailable_until", 0.)
    original_client = httpx.AsyncClient
    calls = []

    def reject(request):
        return httpx.Response(406)

    def fallback(params, context):
        calls.append(params)
        return b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Attention Is All You Need</title><id>https://arxiv.org/abs/1706.03762</id>
        </entry></feed>'''

    monkeypatch.setattr(primary_sources.httpx, "AsyncClient", lambda **kwargs:
                        original_client(transport=httpx.MockTransport(reject)))
    monkeypatch.setattr(primary_sources, "_fetch_arxiv_api_with_urllib", fallback)
    records = asyncio.run(primary_sources.search_papers("id:1706.03762", max_results=1))
    assert records[0]["url"] == "https://arxiv.org/abs/1706.03762"
    assert calls[0]["max_results"] == 1


def test_search_uses_official_html_only_when_atom_transports_return_406(monkeypatch):
    from asteria_researcher.agentic import primary_sources
    monkeypatch.setenv("REVIEW_ARXIV_SEARCH_PROVIDER", "atom")
    monkeypatch.setattr(primary_sources, "_atom_unavailable_until", 0.)
    original_client = httpx.AsyncClient
    atom_calls = []
    html = b'''<li class="arxiv-result">
      <p class="list-title"><a href="https://arxiv.org/abs/2501.12345">arXiv</a></p>
      <p class="title">Agent Evaluation Methods</p>
      <span class="abstract-full">Full abstract evidence.</span>
      <p class="is-size-7">Submitted 12 January, 2025</p></li>'''
    def respond(request):
        if request.url.path == "/api/query":
            atom_calls.append(request.url)
            return httpx.Response(406)
        assert request.url.path == "/search/"
        assert request.url.params["searchtype"] == "title"
        return httpx.Response(200, content=html)
    def reject_atom(*args):
        raise urllib.error.HTTPError("https://export.arxiv.org/api/query", 406, "Not Acceptable", {}, None)
    monkeypatch.setattr(primary_sources.httpx, "AsyncClient", lambda **kwargs:
                        original_client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(primary_sources, "_fetch_arxiv_api_with_urllib", reject_atom)
    records = asyncio.run(primary_sources.search_papers('ti:"Agent Evaluation"', max_results=1))
    assert records == [{"title": "Agent Evaluation Methods", "url": "https://arxiv.org/abs/2501.12345",
                        "published": "Submitted 12 January, 2025", "updated": "",
                        "abstract": "Full abstract evidence."}]
    again = asyncio.run(primary_sources.search_papers('ti:"Agent Evaluation"', max_results=1))
    assert again == records and len(atom_calls) == 1


def test_official_html_search_honors_429(monkeypatch):
    from asteria_researcher.agentic import primary_sources
    original_client = httpx.AsyncClient
    monkeypatch.setenv("REVIEW_ARXIV_SEARCH_PROVIDER", "html")
    def respond(request):
        assert request.url.path == "/search/"
        return httpx.Response(429, headers={"Retry-After": "90"})
    monkeypatch.setattr(primary_sources.httpx, "AsyncClient", lambda **kwargs:
                        original_client(transport=httpx.MockTransport(respond)))
    with pytest.raises(primary_sources.ScholarlyRateLimit) as error:
        asyncio.run(primary_sources.search_papers("agent evaluation"))
    assert error.value.seconds == 90
