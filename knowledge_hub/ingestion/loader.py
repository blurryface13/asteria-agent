"""PDF -> (title, pages of text). Uses pypdf only - no OCR, which is fine
for born-digital papers from Zotero."""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class LoadedDocument:
    doc_id: str          # sha256 of file bytes -> stable across re-runs
    title: str
    source_path: str
    pages: list[str]     # extracted text per page


def _title_from_filename(path: Path) -> str:
    """Zotero names files like 'Guan 等 - 2023 - A Survey of ....pdf'.
    Take the part after the last ' - ' when present."""
    stem = path.stem
    parts = stem.split(" - ")
    title = parts[-1] if len(parts) >= 2 else stem
    return re.sub(r"\s+", " ", title).strip()


def load_pdf(path: str | Path) -> LoadedDocument | None:
    path = Path(path)
    raw = path.read_bytes()
    doc_id = hashlib.sha256(raw).hexdigest()[:24]
    try:
        reader = PdfReader(path)
        # pypdf occasionally emits lone surrogates from malformed CMaps;
        # they are invalid UTF-8 and crash any downstream JSON encoding.
        pages = [
            (page.extract_text() or "").encode("utf-8", errors="ignore").decode("utf-8")
            for page in reader.pages
        ]
    except Exception:
        return None
    if sum(len(p) for p in pages) < 500:
        # likely a scanned/image-only PDF; skip rather than index garbage
        return None
    return LoadedDocument(
        doc_id=doc_id,
        title=_title_from_filename(path),
        source_path=str(path),
        pages=pages,
    )
