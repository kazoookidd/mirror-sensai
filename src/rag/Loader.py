import logging
import re
import unicodedata
from pathlib import Path
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTFigure, LTTextContainer
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage

DOT_LEADER_MIN = 4
# "(cid:N)": glyph with no Unicode mapping. U+E000-U+F8FF: font-private
# symbols such as Word's Wingdings bullets, meaningless outside that font.
_UNMAPPED_GLYPH = re.compile(r"\(cid:\d+\)|[\ue000-\uf8ff]")
_DOT_LEADER = re.compile(rf"\.{{{DOT_LEADER_MIN},}}")

logger = logging.getLogger(__name__)
logging.getLogger("pdfminer").setLevel(logging.ERROR)

def _clean(text: str) -> str:
    """Normalize line endings and whitespace without destroying the
    paragraph structure the chunker relies on (blank lines). NFKC turns
    PDF ligatures back into letters ("ﬁ" -> "fi"), and table of contents
    dot leaders ("Titre ........ 11") are shortened. Runs of spaces and
    tabs inside a line (justified PDF text) become one space; indentation
    at the start of a line is kept."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    text = _DOT_LEADER.sub("...", text)
    text = re.sub(r"(?<=\S)(?:[^\S\n]{2,}|\t)", " ", text)
    text = re.sub(r"[^\S\n]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def _load_text_file(path: Path, source: str) -> list[dict]:
    """A .txt/.md file has no pages: it is returned as a single page
    with page=None."""
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
    """Text blocks of a page layout, including the ones drawn inside
    figures (Form XObjects), which pdfminer does not expose at top level."""
    blocks = []
    for element in container:
        if isinstance(element, LTTextContainer):
            blocks.append(element.get_text())
        elif isinstance(element, LTFigure):
            blocks.extend(_text_blocks(element))
    return blocks

def _read_pdf_pages(path: Path, source: str):
    """Yield (page_number, raw_text) for every page, 1-based, in order.
    pdfminer's layout analysis groups text into blocks, which become
    paragraphs (blank lines) here. Pages are processed one by one: a page
    that cannot be read is logged and yielded empty, so a broken page does
    not cost the others and the numbering stays exact."""
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

def _load_pdf(path: Path, source: str) -> list[dict]:
    """One entry per PDF page that contains text, with its 1-based page
    number so answers can cite "p. 4". Protected, damaged and text-less
    PDFs give a warning instead of an exception."""
    pages = []
    number = 0
    try:
        for number, raw in _read_pdf_pages(path, source):
            text = _clean(_UNMAPPED_GLYPH.sub("", raw))
            if text:
                pages.append({"source": source, "page": number, "text": text})
    except PDFPasswordIncorrect:
        logger.warning(f"{source} is password-protected, skipped")
        return []
    except Exception as e:
        if number == 0:
            logger.warning(f"cannot read PDF {source}, skipped ({e})")
            return []
        logger.warning(f"{source} is damaged after page {number}, "
                       f"later pages skipped ({e})")

    if not pages:
        logger.warning(f"{source} has no extractable text "
                       f"(scanned PDF? OCR is not supported), skipped")
    return pages

READERS = {".txt": _load_text_file, ".md": _load_text_file, ".pdf": _load_pdf}
SUPPORTED_EXTENSIONS = frozenset(READERS)

def load_document(path: str | Path, source: str | None = None) -> list[dict]:
    """Read one supported document and return its pages as
    {"source", "page", "text"} dicts. Returns [] (with a logged warning) for
    unsupported, unreadable or empty files instead of raising."""
    path = Path(path)
    source = source or path.name
    extension = path.suffix.lower()
    reader = READERS.get(extension)
    if reader is None:
        logger.warning(f"unsupported file type {source}, skipped "
                       f"(supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))})")
        return []
    return reader(path, source)

def load_directory(folder: str | Path) -> list[dict]:
    """Load every supported document under `folder` (recursively), in a
    stable order. Sources are paths relative to `folder`, so two files
    with the same name in different subfolders stay distinguishable.
    Hidden files (.DS_Store, ...) are ignored silently."""
    folder = Path(folder)
    if not folder.is_dir():
        logger.warning(f"{folder} is not a directory, nothing loaded")
        return []

    pages = []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if not path.is_file() or any(p.startswith(".") for p in relative.parts):
            continue
        pages.extend(load_document(path, source=relative.as_posix()))

    if not pages:
        logger.warning(f"no readable document found in {folder}")
    return pages
