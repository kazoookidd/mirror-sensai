import logging
import re
import unicodedata
from pathlib import Path
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTFigure, LTTextContainer
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage

TEXT_EXTENSIONS = (".txt", ".md")
PDF_EXTENSION = ".pdf"
SUPPORTED_EXTENSIONS = (*TEXT_EXTENSIONS, PDF_EXTENSION)
_UNREADABLE_CHARS = re.compile(r"\(cid:\d+\)|[\ue000-\uf8ff]")
_DOT_LEADER = re.compile(r"\.{4,}")

logger = logging.getLogger(__name__)
logging.getLogger("pdfminer").setLevel(logging.ERROR)


def _tidy_line(line: str) -> str:
    """One space between words, indentation kept."""
    words = line.split()
    if not words:
        return ""
    indent = line[:len(line) - len(line.lstrip())]
    return indent + " ".join(words)


def _clean(text: str) -> str:
    """Fix ligatures, dot leaders and extra spaces, keep paragraphs."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = _DOT_LEADER.sub("...", text)
    lines = []
    for line in text.split("\n"):
        line = _tidy_line(line)
        if line or (lines and lines[-1]):
            lines.append(line)
    return "\n".join(lines).strip()


def _load_text_file(path: Path, source: str) -> list[dict]:
    """Read a .txt or .md file as a single page."""
    try:
        text = _clean(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        logger.warning(f"{source} is not valid UTF-8 text, skipped")
        return []
    except OSError as e:
        logger.warning(f"cannot read {source}, skipped ({e})")
        return []
    if not text:
        logger.warning(f"{source} is empty, skipped")
        return []
    return [{"source": source, "page": None, "text": text}]


def _text_blocks(container) -> list[str]:
    """Text blocks of a PDF page, figures included."""
    blocks = []
    for element in container:
        if isinstance(element, LTTextContainer):
            blocks.append(element.get_text())
        elif isinstance(element, LTFigure):
            blocks.extend(_text_blocks(element))
    return blocks


def _read_pdf_pages(path: Path, source: str):
    """Yield (page_number, raw_text) for each page, empty if the page is broken."""
    with open(path, "rb") as f:
        manager = PDFResourceManager()
        device = PDFPageAggregator(manager, laparams=LAParams(all_texts=True))
        interpreter = PDFPageInterpreter(manager, device)
        for number, pdf_page in enumerate(PDFPage.get_pages(f), start=1):
            try:
                interpreter.process_page(pdf_page)
                raw = "\n".join(_text_blocks(device.get_result()))
            except Exception as e:
                logger.warning(f"cannot read page {number} of {source}, skipped ({e})")
                raw = ""
            yield number, raw


def _read_pdf_text(path: Path, source: str) -> list[dict] | None:
    """Cleaned text of each PDF page, or None if the PDF cannot be opened."""
    pages = []
    number = 0
    try:
        for number, raw in _read_pdf_pages(path, source):
            text = _clean(_UNREADABLE_CHARS.sub("", raw))
            if text:
                pages.append({"source": source, "page": number, "text": text})
    except PDFPasswordIncorrect:
        logger.warning(f"{source} is password-protected, skipped")
        return None
    except Exception as e:
        if number == 0:
            logger.warning(f"cannot read PDF {source}, skipped ({e})")
            return None
        logger.warning(f"{source} is damaged after page {number}, later pages skipped ({e})")
    return pages


def _load_pdf(path: Path, source: str) -> list[dict]:
    """Read a PDF, one entry per page with text."""
    pages = _read_pdf_text(path, source)
    if pages is None:
        return []
    if not pages:
        logger.warning(f"{source} has no extractable text " f"(scanned PDF? OCR is not supported), skipped")
    return pages


def load_document(path: str | Path, source: str | None = None) -> list[dict]:
    """Pages of one file, [] when it cannot be read."""
    path = Path(path)
    if not source:
        source = path.name
    extension = path.suffix.lower()
    if extension in TEXT_EXTENSIONS:
        return _load_text_file(path, source)
    if extension == PDF_EXTENSION:
        return _load_pdf(path, source)
    logger.warning(f"unsupported file type {source}, skipped "
                   f"(supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))})")
    return []


def list_documents(folder: Path) -> list[tuple[Path, str]]:
    """Every non-hidden file under `folder`, as (path, relative path)."""
    documents = []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if path.is_file() and not any(p.startswith(".") for p in relative.parts):
            documents.append((path, relative.as_posix()))
    return documents


def load_directory(folder: str | Path) -> list[dict]:
    """Load every document under `folder`."""
    folder = Path(folder)
    if not folder.is_dir():
        logger.warning(f"{folder} is not a directory, nothing loaded")
        return []
    pages = []
    for path, source in list_documents(folder):
        pages.extend(load_document(path, source=source))
    if not pages:
        logger.warning(f"no readable document found in {folder}")
    return pages
