import pytest
import asyncio
import httpx
from asteria_researcher.agentic.primary_sources import validate_url, paper_url, extract_text


@pytest.mark.parametrize("url", ["http://arxiv.org/abs/1706.03762", "https://127.0.0.1/x",
    "https://arxiv.org.evil.example/a", "https://user@arxiv.org/a", "https://arxiv.org:444/a"])
def test_reject_untrusted_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_full_paper_representation():
    assert paper_url("https://arxiv.org/abs/1706.03762") == "https://arxiv.org/pdf/1706.03762"


def test_html_extraction():
    assert extract_text(b"<p>Evidence</p><script>bad()</script>", "text/html") == "Evidence"


def test_pdf_extraction():
    import fitz
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 30), "Primary evidence")
        result = extract_text(doc.tobytes(), "application/pdf")
    assert "[Page 1]" in result and "Primary evidence" in result


def test_search_returns_real_records(monkeypatch):
    from asteria_researcher.agentic import primary_sources
    original_client = httpx.AsyncClient

    def respond(request):
        assert request.url.params["search_query"] == 'ti:"Attention Is All You Need"'
        assert request.url.params["max_results"] == "5"
        return httpx.Response(200, content=b'''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><title>Attention Is All You Need</title>
          <id>http://arxiv.org/abs/1706.03762v7</id><summary>Original abstract.</summary></entry>
        </feed>''')

    monkeypatch.setattr(primary_sources.httpx, "AsyncClient", lambda **kwargs:
                        original_client(transport=httpx.MockTransport(respond)))
    records = asyncio.run(primary_sources.search_papers('ti:"Attention Is All You Need"'))
    assert records == [{"title": "Attention Is All You Need",
                        "url": "https://arxiv.org/abs/1706.03762v7", "abstract": "Original abstract."}]
