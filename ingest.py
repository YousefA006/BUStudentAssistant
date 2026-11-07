"""Document extraction, chunking with exact locations, and indexing into SQLite.

Supported: PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), CSV/TSV, Markdown, plain text, HTML, JSON.
Every chunk records a human-readable location used in citations:
  PDF -> "Page 3 of 12"     PPTX -> "Slide 4 of 20"     XLSX -> "Sheet 'Fees', rows 2–31"
  CSV -> "Rows 2–41"        DOCX -> "Paragraphs 12–25"  TXT/MD/HTML/JSON -> "Lines 40–72"
"""
import csv
import hashlib
import io
import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from config import DATA_DIR
from textnorm import clean_text

SUPPORTED = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".tsv", ".txt", ".md", ".markdown", ".html", ".htm", ".json"}
TEXT_TYPES = {".csv", ".tsv", ".txt", ".md", ".markdown", ".html", ".htm", ".json"}

CHUNK_CHARS = 900      # ~200-300 tokens: precise retrieval and fits free-tier token limits
OVERLAP_CHARS = 150
MIN_SECTION_CHARS = 250  # a new heading starts a new chunk once the current one has this much text
TABLE_CHUNK_CHARS = 1500

_HEADING_START = re.compile(
    r"^(\.?\d+(\.\d+)*[.)]?\s|[IVXLC]+\.\s|(chapter|section|part|article|appendix|unit)\b|"
    r"(الفصل|الباب|المادة|القسم|الجزء|البند|ملحق)\b)",
    re.IGNORECASE,
)
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class UnsupportedFile(Exception):
    pass


def is_supported(path: Path) -> bool:
    name = path.name
    return (path.suffix.lower() in SUPPORTED and not name.startswith(("~$", ".", "_")))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("cp1256")  # Arabic Windows encoding (common for CSV exported from Excel)
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not 3 <= len(s) <= 90 or s[-1] in ".,;،؛":
        return False
    if _HEADING_START.match(s) and len(s.split()) <= 14:
        return True
    latin = [c for c in s if c.isascii() and c.isalpha()]
    return len(latin) >= 4 and all(c.isupper() for c in latin) and len(s.split()) <= 10


def _md_heading(line: str):
    m = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- generic chunker
def chunk_lines(items, *, unit: str, heading_fn=_is_heading, section=None, max_chars=CHUNK_CHARS,
                overlap=OVERLAP_CHARS, page=None, fixed_location=None, prefix=""):
    """items: list of (number, text). Groups consecutive items into chunks and labels each with
    the number range it covers, e.g. 'Lines 10–24'. Returns (chunks, last_section)."""
    chunks, buf, buf_len, buf_section = [], [], 0, section

    def flush():
        body = "\n".join(t for _, t in buf).strip()
        if len(body) < (1 if prefix else 15):
            return
        a, b = buf[0][0], buf[-1][0]
        loc = fixed_location or (f"{unit} {a}" if a == b else f"{unit} {a}–{b}")
        # label = every section heading the chunk touches (short sections get merged with the next one)
        heads = []
        if heading_fn:
            for _, t in buf:
                h = heading_fn(t)
                if h:
                    heads.append(h if isinstance(h, str) else t)
        starts_with_heading = bool(heads) and any(heading_fn(t) for _, t in buf[:3])
        labels = heads if starts_with_heading else ([buf_section] if buf_section else []) + heads
        label = " · ".join(dict.fromkeys(l for l in labels if l))[:250] or None
        chunks.append({"page": page if page is not None else a, "section": label,
                       "location": loc, "text": (prefix + body) if prefix else body})

    for num, line in items:
        line = line.strip()
        if not line:
            continue
        h = heading_fn(line) if heading_fn else None
        if h:
            section = h if isinstance(h, str) else line
            if buf and buf_section is None:
                buf_section = section
            if buf and buf_len >= MIN_SECTION_CHARS and overlap:
                flush()  # keep one topic per chunk: start a fresh chunk at each heading (no overlap)
                buf, buf_len = [], 0
        if buf and buf_len + len(line) > max_chars:
            flush()
            tail, tail_len = [], 0
            for prev in reversed(buf):
                if tail_len + len(prev[1]) > overlap:
                    break
                tail.insert(0, prev)
                tail_len += len(prev[1])
            buf, buf_len = tail, tail_len
            buf_section = section  # continuation chunk belongs to the current section
        if not buf:
            buf_section = section
        while len(line) > max_chars:  # one very long line: split on sentence/space boundaries
            cut = max(line.rfind(". ", 0, max_chars), line.rfind("؟ ", 0, max_chars), line.rfind(" ", 0, max_chars))
            cut = cut + 1 if cut > max_chars // 2 else max_chars
            buf.append((num, line[:cut].strip()))
            flush()
            buf, buf_len, buf_section = [], 0, section
            line = line[cut:].strip()
        if line:
            buf.append((num, line))
            buf_len += len(line) + 1
    if buf:
        flush()
    return chunks, section


def _numbered(text: str):
    return list(enumerate(text.split("\n"), start=1))


# --------------------------------------------------------------------------- per-format extractors
_LIST_MARK = re.compile(r"^([●■•▪◦❖o\-–*]|\(?[0-9]+[.)]|\(?[A-Za-z][.)]|[أبجده][.)])\s")


def _reflow(text: str) -> str:
    """Join wrapped English lines back into sentences (keeps bullets, headings and Arabic lines as they are)."""
    out = []
    for line in (l.strip() for l in text.split("\n")):
        if not line:
            continue
        prev = out[-1] if out else ""
        if (prev and line[0].islower() and line[0].isascii() and not _LIST_MARK.match(line)
                and prev[-1] not in ".:;!?" and not _is_heading(prev)):
            out[-1] = prev + " " + line
        else:
            out.append(line)
    return "\n".join(out)


def _pdf_pages(path: Path) -> list[str]:
    """Text of every page. pypdf 'layout' mode keeps lines intact (the plain mode splits some PDFs into
    one word per line); PyMuPDF is the fallback for PDFs pypdf can't read."""
    pages = []
    try:
        from pypdf import PdfReader

        for page in PdfReader(str(path)).pages:
            try:
                pages.append(page.extract_text(extraction_mode="layout") or "")
            except Exception:
                pages.append(page.extract_text() or "")
    except Exception:
        pages = []
    if not any(p.strip() for p in pages):
        try:
            import fitz  # PyMuPDF

            with fitz.open(str(path)) as doc:
                pages = [p.get_text("text") for p in doc]
        except ImportError:
            pass
    return [_reflow(clean_text(p)) for p in pages]


def _strip_repeating_lines(pages: list[str]) -> list[str]:
    """Drop headers/footers: lines (ignoring digits) that repeat on most pages, e.g. 'Updated 19/01/2026 3'."""
    if len(pages) < 3:
        return pages
    key = lambda l: re.sub(r"[\d\s]+", "", l)  # noqa: E731
    counts = {}
    for p in pages:
        for k in {key(l) for l in p.split("\n") if l.strip()}:
            counts[k] = counts.get(k, 0) + 1
    limit = max(3, len(pages) // 2)
    return ["\n".join(l for l in p.split("\n") if not l.strip() or len(l) > 120 or counts.get(key(l), 0) < limit)
            for p in pages]


def _pdf(path: Path):
    pages = _strip_repeating_lines(_pdf_pages(path))
    chunks, section = [], None
    for n, text in enumerate(pages, start=1):
        c, section = chunk_lines(_numbered(text), unit="Line", section=section, page=n,
                                 fixed_location=f"Page {n} of {len(pages)}")
        chunks += c
    return chunks, len(pages)


def _docx(path: Path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(f"{_W}body")
    items, headings, n = [], set(), 0

    def para_text(p):
        return "".join(t.text or "" for t in p.iter(f"{_W}t"))

    for el in body:
        if el.tag == f"{_W}p":
            text = clean_text(para_text(el)).strip()
            if not text:
                continue
            n += 1
            style = el.find(f"{_W}pPr/{_W}pStyle")
            sval = (style.get(f"{_W}val") or "").lower() if style is not None else ""
            if sval.startswith(("heading", "title")) or "عنوان" in sval:
                headings.add(n)
            items.append((n, text))
        elif el.tag == f"{_W}tbl":
            for row in el.iter(f"{_W}tr"):
                cells = [clean_text(para_text(c)).strip() for c in row.iter(f"{_W}tc")]
                if any(cells):
                    n += 1
                    items.append((n, " | ".join(cells)))
    head_text = {t for i, t in items if i in headings}
    chunks, _ = chunk_lines(items, unit="Paragraphs",
                            heading_fn=lambda l: l if l in head_text else _is_heading(l))
    for c in chunks:  # 'Paragraphs 5' -> 'Paragraph 5'
        c["location"] = re.sub(r"^Paragraphs (\d+)$", r"Paragraph \1", c["location"])
    return chunks, 0


def _pptx(path: Path):
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                       key=lambda s: int(re.search(r"(\d+)\.xml$", s).group(1)))
        slides = []
        for name in names:
            root = ET.fromstring(z.read(name))
            paras = ["".join(t.text or "" for t in p.iter(f"{_A}t")) for p in root.iter(f"{_A}p")]
            slides.append(clean_text("\n".join(p for p in paras if p.strip())))
    chunks = []
    for n, text in enumerate(slides, start=1):
        title = text.split("\n", 1)[0][:90] if text else None
        c, _ = chunk_lines(_numbered(text), unit="Line", heading_fn=None, section=title, page=n,
                           fixed_location=f"Slide {n} of {len(slides)}")
        chunks += c
    return chunks, len(slides)


def _rows_to_items(rows, first_row_no=1):
    """Table rows -> ('Row N', 'Header: value; Header: value') so each passage is self-describing."""
    rows = [[("" if v is None else str(v)).strip() for v in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    header = [h or f"Column {i + 1}" for i, h in enumerate(rows[0])]
    items = [(first_row_no, "Columns: " + " | ".join(header))]
    for i, r in enumerate(rows[1:], start=first_row_no + 1):
        pairs = [f"{header[j] if j < len(header) else f'Column {j + 1}'}: {v}" for j, v in enumerate(r) if v]
        items.append((i, "; ".join(pairs)))
    return items


def _table_chunks(items, sheet=None):
    if not items:
        return []
    header_line = items[0][1]
    unit = f"Sheet '{sheet}', rows" if sheet else "Rows"
    chunks, _ = chunk_lines(items[1:] or items, unit=unit, heading_fn=None, section=sheet,
                            max_chars=TABLE_CHUNK_CHARS, overlap=0, prefix=header_line + "\n")
    for c in chunks:
        c["location"] = re.sub(r"rows (\d+)$", r"row \1", re.sub(r"^Rows (\d+)$", r"Row \1", c["location"]))
    return chunks


def _csv(path: Path, delimiter=None):
    text = read_text_file(path)
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return _table_chunks(_rows_to_items([[clean_text(v) for v in r] for r in rows])), 0


def _xlsx(path: Path):
    try:
        import openpyxl
    except ImportError:
        raise UnsupportedFile("Excel support needs the 'openpyxl' package (pip install openpyxl)") from None
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    chunks = []
    try:
        for ws in wb.worksheets:
            rows = [[clean_text(str(v)) if v is not None else "" for v in r] for r in ws.iter_rows(values_only=True)]
            chunks += _table_chunks(_rows_to_items(rows), sheet=ws.title)
    finally:
        wb.close()
    return chunks, 0


class _HTMLText(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "ul", "ol"}

    def __init__(self):
        super().__init__()
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag in ("h1", "h2", "h3", "h4"):
            self.out.append("# ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK or tag in ("td", "th"):
            self.out.append("\n" if tag in self.BLOCK else " | ")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def _plain(path: Path):
    ext = path.suffix.lower()
    text = read_text_file(path)
    heading = _is_heading
    if ext in (".md", ".markdown"):
        heading = lambda l: _md_heading(l) or False  # noqa: E731
    elif ext in (".html", ".htm"):
        p = _HTMLText()
        p.feed(text)
        text = re.sub(r"\n\s*\n+", "\n", "".join(p.out))
        heading = lambda l: _md_heading(l) or False  # noqa: E731
    elif ext == ".json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
        except ValueError:
            pass
    chunks, _ = chunk_lines(_numbered(clean_text(text)), unit="Lines", heading_fn=heading)
    for c in chunks:
        c["location"] = re.sub(r"^Lines (\d+)$", r"Line \1", c["location"])
    return chunks, 0


def extract_chunks(path: Path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        chunks, pages = _pdf(path)
    elif ext == ".docx":
        chunks, pages = _docx(path)
    elif ext == ".pptx":
        chunks, pages = _pptx(path)
    elif ext == ".xlsx":
        chunks, pages = _xlsx(path)
    elif ext == ".csv":
        chunks, pages = _csv(path)
    elif ext == ".tsv":
        chunks, pages = _csv(path, delimiter="\t")
    elif ext in TEXT_TYPES:
        chunks, pages = _plain(path)
    else:
        raise UnsupportedFile(f"Unsupported file type: {ext}")
    for i, c in enumerate(chunks, start=1):
        c["seq"] = i
    return chunks, pages


# --------------------------------------------------------------------------- indexing
def index_file(conn, path: Path, *, filename: str, owner_id, visibility: str, source: str) -> dict:
    """(Re)index one file. Returns the document row as a dict."""
    digest = sha256_file(path)
    chunks, pages = extract_chunks(path)
    status = "ready" if chunks else "no_text"
    conn.execute("DELETE FROM documents WHERE stored_path = ?", (str(path),))
    cur = conn.execute(
        "INSERT INTO documents (owner_id, visibility, source, filename, stored_path, sha256, pages, chunks, status, kind)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (owner_id, visibility, source, filename, str(path), digest, pages, len(chunks), status,
         path.suffix.lower().lstrip(".")),
    )
    doc_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO chunks (document_id, page, seq, section, location, text) VALUES (?,?,?,?,?,?)",
        [(doc_id, c["page"], c["seq"], c["section"], c["location"], c["text"]) for c in chunks],
    )
    return dict(conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone())


index_pdf = index_file  # backwards-compatible name


def sync_data_folder(conn) -> dict:
    """Index new/changed files in DATA_DIR and drop documents whose files were removed."""
    found, added, updated, failed = set(), [], [], []
    for path in sorted(p for p in DATA_DIR.rglob("*") if p.is_file() and is_supported(p)):
        key = str(path)
        found.add(key)
        row = conn.execute("SELECT sha256 FROM documents WHERE stored_path = ?", (key,)).fetchone()
        try:
            if row and row["sha256"] == sha256_file(path):
                continue
            index_file(conn, path, filename=str(path.relative_to(DATA_DIR)).replace("\\", "/"),
                       owner_id=None, visibility="shared", source="folder")
            (updated if row else added).append(path.name)
        except Exception as exc:  # one broken file must not stop the whole sync
            failed.append(f"{path.name}: {exc}")
    removed = []
    for row in conn.execute("SELECT id, stored_path, filename FROM documents WHERE source = 'folder'").fetchall():
        if row["stored_path"] not in found:
            conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
            removed.append(row["filename"])
    conn.commit()
    return {"added": added, "updated": updated, "removed": removed, "failed": failed}
