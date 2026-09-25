"""Bounded research-source reader with per-client system certificate trust."""
import asyncio
import re
import ssl
import os
import tempfile
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urljoin, urlparse

import httpx
import truststore

ACADEMIC_ARCHIVES = frozenset({"arxiv.org", "export.arxiv.org"})
ACADEMIC_PUBLISHERS = frozenset({"aclanthology.org", "openaccess.thecvf.com", "proceedings.neurips.cc"})
# Exact official hosts only. A host being allowed is not a claim that its site
# permits automated access or that its articles have been peer reviewed.
INSTITUTIONAL_HOSTS = frozenset({"anthropic.com", "www.anthropic.com", "www-cdn.anthropic.com",
                                 "openai.com", "www.openai.com", "cdn.openai.com",
                                 "x.ai", "www.x.ai", "data.x.ai"})
# Explicit public issuers/regulators, not an arbitrary user-controlled domain
# wildcard. Search snippets are discovery only; documents must be read.
FINANCIAL_HOSTS = frozenset({
    "sec.gov", "www.sec.gov", "data.sec.gov", "www.federalreserve.gov", "www.bls.gov",
    "www.bea.gov", "www.imf.org", "www.worldbank.org", "www.oecd.org",
    "www.hkexnews.hk", "www.hkex.com.hk", "www.sse.com.cn", "www.szse.cn",
    "www.csrc.gov.cn", "www.stats.gov.cn", "www.pbc.gov.cn",
    "investor.nvidia.com", "investor.apple.com", "www.microsoft.com",
    "ir.aboutamazon.com", "abc.xyz", "investor.tsmc.com",
    # NVIDIA's investor-relations page links its annual-report PDFs here.
    "s201.q4cdn.com",
})
HOSTS = ACADEMIC_ARCHIVES | ACADEMIC_PUBLISHERS | INSTITUTIONAL_HOSTS | FINANCIAL_HOSTS
_atom_unavailable_until = 0.0
MAX_BYTES = int(os.getenv("REVIEW_PAPER_MAX_MIB", "64")) * 1024 * 1024
if not 1024 * 1024 <= MAX_BYTES <= 256 * 1024 * 1024:
    raise ValueError("REVIEW_PAPER_MAX_MIB must be between 1 and 256")


class ScholarlyRateLimit(RuntimeError):
    def __init__(self, seconds):
        self.seconds = seconds
        super().__init__(f"arXiv 检索限流（HTTP 429），需等待至少 {seconds:.0f} 秒后重试；更换关键词不能解除限流")


def retry_after_seconds(value, now=None):
    now = time.time() if now is None else now
    try:
        return max(1., float(value))
    except (ValueError, TypeError):
        try:
            return max(1., parsedate_to_datetime(value).timestamp() - now)
        except (ValueError, TypeError, AttributeError, OverflowError):
            return 60.


def explicit_arxiv_urls(text):
    """Seed only identifiers the user explicitly labelled as arXiv papers."""
    return {"https://arxiv.org/abs/" + match.group(1)
            for match in re.finditer(r"\barxiv\s*:\s*(\d{4}\.\d{4,5}(?:v\d+)?)(?![\w.])", text, re.I)}


def _fetch_arxiv_api_with_urllib(params, context):
    """Fallback for environments where arXiv rejects httpx's transport with 406."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, new_url):
            raise ValueError("学术检索接口发生重定向；未跟随未经核验的目标地址")

    request = urllib.request.Request(
        "https://export.arxiv.org/api/query?" + urlencode(params),
        headers={"Accept": "application/atom+xml", "User-Agent": "AsteriaResearch/1.0"},
    )
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), NoRedirect())
    try:
        with opener.open(request, timeout=25) as response:
            content = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise ScholarlyRateLimit(retry_after_seconds(error.headers.get("Retry-After"))) from error
        raise
    return content


async def _search_arxiv_html(query, start, max_results, sort_by, context):
    """Official arXiv search fallback when its Atom API is rejected with 406."""
    from bs4 import BeautifulSoup

    field = re.fullmatch(r"(?i)(ti|au|abs|all):(.+)", query.strip())
    search_type = {"ti": "title", "au": "author", "abs": "abstract", "all": "all"}.get(
        field.group(1).lower() if field else "", "all")
    terms = (field.group(2) if field else query).strip()
    params = {"query": terms, "searchtype": search_type, "abstracts": "show",
              "size": 50, "start": start,
              "order": {"relevance": "", "submittedDate": "-submitted_date",
                        "lastUpdatedDate": "-announced_date_first"}[sort_by]}
    async with httpx.AsyncClient(verify=context, timeout=25, follow_redirects=False) as client:
        response = await client.get("https://arxiv.org/search/", params=params,
                                    headers={"Accept": "text/html", "User-Agent": "AsteriaResearch/1.0"})
        if response.status_code == 429:
            raise ScholarlyRateLimit(retry_after_seconds(response.headers.get("Retry-After")))
        response.raise_for_status()
    if len(response.content) > 2 * 1024 * 1024:
        raise ValueError("学术检索网页响应过大")
    soup = BeautifulSoup(response.content, "html.parser")
    records = []
    for item in soup.select("li.arxiv-result"):
        link = item.select_one('p.list-title a[href*="/abs/"]')
        title = item.select_one("p.title")
        if not link or not title:
            continue
        url = link.get("href", "")
        if not re.fullmatch(r"https://arxiv\.org/abs/\d{4}\.\d{4,5}(?:v\d+)?", url):
            continue
        abstract = item.select_one("span.abstract-full") or item.select_one("span.abstract-short")
        submitted = item.select_one("p.is-size-7")
        records.append({"title": title.get_text(" ", strip=True), "url": url,
                        "published": submitted.get_text(" ", strip=True) if submitted else "",
                        "updated": "", "abstract": abstract.get_text(" ", strip=True)[:1800] if abstract else ""})
        if len(records) >= min(max_results, 30):
            break
    return records


async def search_papers(query, *, start=0, max_results=15, sort_by="relevance"):
    """Discover real arXiv records; identifiers are never generated by the LLM."""
    import xml.etree.ElementTree as ET
    global _atom_unavailable_until
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # The official search page is the stable default for this deployment. The
    # Atom API remains opt-in, not a way to evade a 429 from either provider.
    if os.getenv("REVIEW_ARXIV_SEARCH_PROVIDER", "html") == "html":
        return await _search_arxiv_html(query, start, max_results, sort_by, context)
    if time.monotonic() < _atom_unavailable_until:
        return await _search_arxiv_html(query, start, max_results, sort_by, context)
    params = {"search_query": query, "start": start, "max_results": min(max_results, 30),
              "sortBy": sort_by, "sortOrder": "descending"}
    async with httpx.AsyncClient(verify=context, timeout=25) as client:
        response = await client.get("https://export.arxiv.org/api/query", params=params)
        if response.status_code == 429:
            raise ScholarlyRateLimit(retry_after_seconds(response.headers.get("Retry-After")))
        if response.status_code != 406:
            response.raise_for_status()
    if response.status_code == 406:
        try:
            content = await asyncio.to_thread(_fetch_arxiv_api_with_urllib, params, context)
        except urllib.error.HTTPError as error:
            if error.code != 406:
                raise
            # A transport-level 406 is stable for this deployment. Avoid
            # repeating the failed Atom path for every parallel researcher.
            _atom_unavailable_until = time.monotonic() + 1800
            return await _search_arxiv_html(query, start, max_results, sort_by, context)
    else:
        content = response.content
    if len(content) > 1024 * 1024:
        raise ValueError("学术检索响应过大")
    root = ET.fromstring(content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return [{"title": entry.findtext("a:title", "", ns).strip(),
             "url": entry.findtext("a:id", "", ns).replace("http://", "https://"),
             "published": entry.findtext("a:published", "", ns),
             "updated": entry.findtext("a:updated", "", ns),
             "abstract": entry.findtext("a:summary", "", ns)[:1800]}
            for entry in root.findall("a:entry", ns)]


def validate_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or
            parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("原文工具仅允许已登记学术、监管及机构来源的 HTTPS 地址")
    if parsed.hostname == 's201.q4cdn.com' and not parsed.path.startswith('/141608511/files/doc_financials/'):
        raise ValueError('仅允许已核验的 NVIDIA 投资者关系文档路径')
    return url


def source_type(url):
    """Classify the host, not the content's claimed academic status."""
    validate_url(url)
    host = urlparse(url).hostname
    if host in FINANCIAL_HOSTS:
        return "financial_primary"
    if host in INSTITUTIONAL_HOSTS:
        return "institutional_report"
    if host in ACADEMIC_ARCHIVES:
        return "academic_preprint"
    return "academic_publication"


def paper_url(url):
    validate_url(url)
    parsed = urlparse(url)
    if parsed.hostname in {"arxiv.org", "export.arxiv.org"}:
        match = re.fullmatch(r"/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?", parsed.path)
        if match:
            return "https://arxiv.org/pdf/" + match.group(1)
    return url


def extract_text(data, content_type):
    if data.startswith(b"%PDF"):
        import fitz
        with fitz.open(stream=data, filetype="pdf") as document:
            return "\n".join(f"[Page {i + 1}]\n{document[i].get_text()}"
                             for i in range(min(len(document), 30)))[:65000]
    if "html" not in content_type:
        raise ValueError("研究来源未返回 PDF 或 HTML")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "html.parser")
    for node in soup(["script", "style", "nav", "footer"]):
        node.decompose()
    main = soup.find("article") or soup.find("main")
    return (main or soup).get_text("\n", strip=True)[:65000]


async def read_paper(url, *, consume_bytes=None):
    return await asyncio.wait_for(_read_paper(url, consume_bytes=consume_bytes), timeout=180)


async def _read_paper(url, *, consume_bytes=None):
    target = paper_url(url)
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    user_agent = os.getenv('ASTERIA_SOURCE_USER_AGENT', 'AsteriaResearch/1.0')
    async with httpx.AsyncClient(verify=context, timeout=25, follow_redirects=False,
                                 headers={'User-Agent': user_agent}) as client:
        for _ in range(4):
            validate_url(target)
            async with client.stream("GET", target) as response:
                if response.is_redirect:
                    target = urljoin(target, response.headers["location"])
                    validate_url(target)
                    continue
                response.raise_for_status()
                # Stream to disk rather than accumulating a PDF in RAM. The
                # temporary file is closed/deleted on errors and cancellation.
                with tempfile.NamedTemporaryFile(suffix=".paper") as downloaded:
                    size = 0
                    async for chunk in response.aiter_bytes(65536):
                        size += len(chunk)
                        if consume_bytes:
                            consume_bytes(len(chunk))
                        if size > MAX_BYTES:
                            raise ValueError(f"单篇文件超过 {MAX_BYTES // 1048576} MiB：{target}；可调整 REVIEW_PAPER_MAX_MIB")
                        downloaded.write(chunk)
                    downloaded.flush()
                    text, pages = await asyncio.to_thread(extract_file, downloaded.name,
                                                          response.headers.get("content-type", ""))
                    linked = []
                    if 'html' in response.headers.get('content-type', '') and urlparse(target).hostname == 'investor.nvidia.com':
                        from bs4 import BeautifulSoup
                        with open(downloaded.name, 'rb') as source:
                            soup = BeautifulSoup(source.read(), 'html.parser')
                        for anchor in soup.find_all('a', href=True):
                            label = anchor.get_text(' ', strip=True)
                            candidate = urljoin(target, anchor['href'])
                            if not candidate.lower().split('?', 1)[0].endswith('.pdf') or 'report' not in label.lower():
                                continue
                            try:
                                validate_url(candidate)
                            except ValueError:
                                continue
                            year = re.search(r'/files/doc_financials/(20\d{2})/', candidate)
                            linked.append({'url': candidate,
                                           'title': ((year[1] + ' ') if year else '') + label[:140],
                                           'linked_from': target})
                            if len(linked) >= 30:
                                break
                if not text.strip():
                    raise ValueError("研究来源没有可提取文本，需 OCR 工具，未伪造内容")
                return {"url": target, "requested_url": url, "text": text,
                        "pages": pages, "bytes": size, "extraction_limit": None, "linked_sources": linked}
    raise ValueError("论文重定向次数超过限制")


def extract_file(path, content_type):
    import fitz
    with open(path, "rb") as source:
        is_pdf = source.read(4) == b"%PDF"
    if is_pdf:
        with fitz.open(path) as document:
            if len(document) > 1500:
                raise ValueError("研究来源超过 1500 页，需明确扩大解析预算")
            pages = [{"page": i + 1, "text": page.get_text()} for i, page in enumerate(document)]
        if sum(len(p["text"]) for p in pages) > 5_000_000:
            raise ValueError("全文文本超过 500 万字符，需扩大索引预算")
        return "\n".join(f'[Page {p["page"]}]\n{p["text"]}' for p in pages), pages
    with open(path, "rb") as source:
        if "html" not in content_type:
            raise ValueError("研究来源未返回 PDF 或 HTML")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(source.read(), "html.parser")
        for node in soup(["script", "style", "nav", "footer"]):
            node.decompose()
        main = soup.find("article") or soup.find("main")
        text = (main or soup).get_text("\n", strip=True)
        if len(text) > 5_000_000:
            raise ValueError("全文文本超过 500 万字符，需扩大索引预算")
    return text, [{"page": 1, "text": text}]
