"""Make CJK CID fonts portable to readers without external Adobe CMaps."""
from pathlib import Path
import re
import subprocess

import pymupdf


def embed_unicode_maps(path: Path) -> int:
    """Embed TeX's authoritative CID-to-Unicode maps; never guess glyph IDs.

    XeTeX embeds Fandol glyphs but may omit ToUnicode for Adobe collections.
    Some Poppler builds then reject the font without their language pack.
    Identity-H character codes are CIDs, so the collection's map applies.
    """
    count = 0
    with pymupdf.open(path) as document:
        seen = set()
        for page in document:
            for font in page.get_fonts(full=True):
                xref = font[0]
                if xref in seen:
                    continue
                seen.add(xref)
                if font[2] != "Type0" or font[5] != "Identity-H":
                    continue
                if document.xref_get_key(xref, "ToUnicode")[0] != "null":
                    continue
                descendants = document.xref_get_key(xref, "DescendantFonts")[1]
                match = re.search(r"(\d+) 0 R", descendants)
                if not match:
                    continue
                cid = int(match[1])
                registry = document.xref_get_key(cid, "CIDSystemInfo/Registry")[1]
                ordering = document.xref_get_key(cid, "CIDSystemInfo/Ordering")[1]
                if registry != "Adobe" or ordering not in {"GB1", "CNS1", "Japan1", "Korea1"}:
                    continue
                name = f"Adobe-{ordering}-UCS2"
                location = subprocess.check_output(["kpsewhich", "--format=cmap", name], text=True, timeout=10).strip()
                if not location or not Path(location).is_file():
                    raise RuntimeError(f"Missing TeX Unicode mapping: {name}")
                stream = document.get_new_xref()
                document.update_object(stream, "<<>>")
                document.update_stream(stream, Path(location).read_bytes())
                document.xref_set_key(xref, "ToUnicode", f"{stream} 0 R")
                count += 1
        if count:
            document.saveIncr()
    return count
