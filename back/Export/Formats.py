"""
[X3] A conversation as a file: JSON, Markdown or PDF.

The CLI (/export) and the web interface call export() with the conversation
on screen: for a conversation with branches (X2), that is the version shown,
under the title of its root.
"""

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF
from Memories.Branches import root_of
from Memories.Conversations import get_conversation
from Memories.Database import get_connection

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT = "NotoSans"
AUTHORS = {"user": "You", "assistant": "SENSAI"}
DATE_FORMAT = "%b %d, %Y %H:%M UTC"
SQLITE_DATE = "%Y-%m-%d %H:%M:%S"
FILE_NAME = "sensai-{id}-{slug}.{extension}"
MAX_SLUG = 60
EMPTY = "This chat has no messages yet."

MARGIN = 20
LINE = 5.5
INDENT = 7
TEXT_COLOR = (22, 27, 23)
MUTED_COLOR = (100, 107, 99)
ACCENT_COLOR = (122, 46, 90)

# Same subset of Markdown as the web interface (front/src/lib/markdown.jsx).
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
BOLD_LINE = re.compile(r"^\*\*([^*]+)\*\*:?$")
BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
NUMBERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")
ARROWS = {"→": "->", "←": "<-", "⇒": "=>"}


def _iso(sqlite_date: str) -> str:
    return datetime.strptime(sqlite_date, SQLITE_DATE).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _readable(iso_date: str) -> str:
    return datetime.fromisoformat(iso_date.replace("Z", "+00:00")).strftime(DATE_FORMAT)


def document(conversation_id: int) -> dict:
    """The conversation as plain data: title, dates and messages, oldest first."""
    conversation = get_conversation(conversation_id)
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,)
        ).fetchall()
    finally:
        conn.close()
    return {
        "title": get_conversation(root_of(conversation_id))["title"],
        "created_at": _iso(conversation["created_at"]),
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "messages": [{"role": row["role"], "content": row["content"], "created_at": _iso(row["created_at"])} for row in rows],
    }


def to_json(doc: dict) -> bytes:
    return json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")


def to_markdown(doc: dict) -> bytes:
    count = len(doc["messages"])
    parts = [f"# {doc['title']}", f"_Exported from SENSAI on {_readable(doc['exported_at'])}, {count} message{'s' * (count != 1)}._"]
    for message in doc["messages"]:
        parts += [f"## {AUTHORS.get(message['role'], message['role'])}", message["content"].strip()]
    return ("\n\n".join(parts) + "\n").encode("utf-8")


class _Pdf(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font(FONT, size=8)
        self.set_text_color(*MUTED_COLOR)
        self.cell(0, 4, f"SENSAI  ·  {self.page_no()}/{{nb}}", align="C")


def _printable(pdf: FPDF, text: str) -> str:
    """The font only covers Latin, Greek and Cyrillic: other characters (emoji...) become "?"."""
    cmap = pdf.current_font.cmap
    return "".join(char if ord(char) in cmap or char == "\n" else ARROWS.get(char, "?") for char in text)


def _write_inline(pdf: FPDF, text: str, bold: bool = False) -> None:
    for part in filter(None, INLINE.split(text)):
        strong = part.startswith("**") and part.endswith("**") and len(part) > 4
        code = part.startswith("`") and part.endswith("`") and len(part) > 2
        pdf.set_font(FONT, "B" if bold or strong else "")
        pdf.write(LINE, _printable(pdf, part[2:-2] if strong else part[1:-1] if code else part))
    pdf.set_font(FONT, "")


def _write_item(pdf: FPDF, marker: str, text: str) -> None:
    """A list item whose wrapped lines stay aligned after the marker."""
    pdf.set_x(MARGIN + 2)
    pdf.write(LINE, marker)
    pdf.set_left_margin(MARGIN + INDENT)
    pdf.set_x(MARGIN + INDENT)
    _write_inline(pdf, text)
    pdf.ln(LINE)
    pdf.set_left_margin(MARGIN)


def _write_markdown(pdf: FPDF, text: str) -> None:
    for line in text.replace("\r", "").strip().split("\n"):
        heading = HEADING.match(line) or BOLD_LINE.match(line)
        bullet = BULLET.match(line)
        numbered = NUMBERED.match(line)
        if not line.strip():
            pdf.ln(LINE / 2)
        elif heading:
            pdf.ln(1)
            _write_inline(pdf, heading[1], bold=True)
            pdf.ln(LINE)
        elif bullet:
            _write_item(pdf, "•", bullet[1])
        elif numbered:
            _write_item(pdf, f"{numbered[1]}.", numbered[2])
        else:
            _write_inline(pdf, line)
            pdf.ln(LINE)


def to_pdf(doc: dict) -> bytes:
    pdf = _Pdf(format="A4")
    pdf.set_margins(MARGIN, MARGIN)
    pdf.set_auto_page_break(True, margin=MARGIN)
    pdf.add_font(FONT, "", FONT_DIR / f"{FONT}-Regular.ttf")
    pdf.add_font(FONT, "B", FONT_DIR / f"{FONT}-Bold.ttf")
    pdf.set_title(doc["title"])
    pdf.set_creator("SENSAI")
    pdf.add_page()

    pdf.set_font(FONT, "B", 16)
    pdf.set_text_color(*TEXT_COLOR)
    pdf.multi_cell(0, 8, _printable(pdf, doc["title"]), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, size=9)
    pdf.set_text_color(*MUTED_COLOR)
    pdf.cell(0, 6, f"Exported from SENSAI on {_readable(doc['exported_at'])}", new_x="LMARGIN", new_y="NEXT")

    for message in doc["messages"]:
        pdf.ln(4)
        pdf.set_font(FONT, "B", 10)
        pdf.set_text_color(*ACCENT_COLOR)
        pdf.cell(0, 6, f"{AUTHORS.get(message['role'], message['role'])}  ·  {_readable(message['created_at'])}",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(FONT, size=10.5)
        pdf.set_text_color(*TEXT_COLOR)
        _write_markdown(pdf, message["content"])
    return bytes(pdf.output())


def _slug(title: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:MAX_SLUG].rstrip("-") or "chat"


FORMATS = {
    "json": (to_json, "application/json"),
    "md": (to_markdown, "text/markdown; charset=utf-8"),
    "pdf": (to_pdf, "application/pdf"),
}


def export(conversation_id: int, file_format: str) -> tuple[str, str, bytes]:
    """(file name, media type, content). ValueError for an unknown format or an empty chat."""
    if file_format not in FORMATS:
        raise ValueError(f"Unknown format '{file_format}': choose md, json or pdf.")
    doc = document(conversation_id)
    if not doc["messages"]:
        raise ValueError(EMPTY)
    render, media_type = FORMATS[file_format]
    name = FILE_NAME.format(id=conversation_id, slug=_slug(doc["title"]), extension=file_format)
    return name, media_type, render(doc)
