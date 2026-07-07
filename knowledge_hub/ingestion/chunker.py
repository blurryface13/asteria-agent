"""Page-aware semantic chunking on top of RecursiveCharacterTextSplitter."""
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .loader import LoadedDocument


@dataclass
class Chunk:
    chunk_id: str        # f"{doc_id}:{index}" -> idempotent upserts
    doc_id: str
    index: int
    content: str
    page_start: int


def chunk_document(doc: LoadedDocument, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    # Join pages with a marker so we can map each chunk back to a page.
    page_offsets: list[tuple[int, int]] = []  # (char_offset, page_number)
    full_text = ""
    for page_no, page_text in enumerate(doc.pages, start=1):
        page_offsets.append((len(full_text), page_no))
        full_text += page_text + "\n"

    def page_for_offset(offset: int) -> int:
        page = 1
        for start, page_no in page_offsets:
            if offset >= start:
                page = page_no
            else:
                break
        return page

    chunks: list[Chunk] = []
    cursor = 0
    for i, piece in enumerate(splitter.split_text(full_text)):
        # find() from a moving cursor keeps duplicate snippets mapped in order
        located = full_text.find(piece[:80], cursor)
        offset = located if located >= 0 else cursor
        cursor = max(cursor, offset)
        chunks.append(Chunk(
            chunk_id=f"{doc.doc_id}:{i}",
            doc_id=doc.doc_id,
            index=i,
            content=piece.strip(),
            page_start=page_for_offset(offset),
        ))
    return [c for c in chunks if len(c.content) >= 80]
