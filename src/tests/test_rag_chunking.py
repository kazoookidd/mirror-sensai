"""
Unit tests for [R1] document ingestion (rag.Loader + rag.Chunker).
No Ollama needed.

Usage (from the project root):
    python3 -m unittest discover -s src/tests -p "test_rag_*.py" -v
"""

import contextlib
import io
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from Memories.Compression import CHARS_PER_TOKEN
from rag.Chunker import _LEVELS, _pieces, _split, chunk_pages, chunk_text
from rag.Loader import load_directory, load_document

DOCS_DIR = Path(__file__).resolve().parents[2] / "data" / "docs"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())

def _quiet(func, *args, **kwargs):
    """Run func while capturing the warnings it logs.
    Returns (result, captured_output)."""
    handler = _LogCapture()
    logger = logging.getLogger("rag")
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    try:
        result = func(*args, **kwargs)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    return result, "\n".join(handler.messages)

class LoaderTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_text_and_markdown_are_single_pages(self):
        (self.dir / "a.txt").write_text("Bonjour.\r\n\r\n\r\n\r\nSuite.", encoding="utf-8")
        (self.dir / "b.md").write_text("# Titre\n\nTexte.", encoding="utf-8")
        for name in ("a.txt", "b.md"):
            pages = load_document(self.dir / name)
            self.assertEqual(len(pages), 1)
            self.assertIsNone(pages[0]["page"])
            self.assertEqual(pages[0]["source"], name)
        self.assertEqual(load_document(self.dir / "a.txt")[0]["text"], "Bonjour.\n\nSuite.")

    def test_pdf_keeps_page_numbers(self):
        pages = load_document(FIXTURES_DIR / "accord_teletravail.pdf")
        self.assertEqual([p["page"] for p in pages], [1, 2, 3])
        self.assertIn("2 jours par semaine", pages[0]["text"])
        self.assertIn("2,50 euros", pages[1]["text"])
        self.assertIn("déconnexion", pages[2]["text"])

    def test_pdf_text_blocks_become_paragraphs(self):
        text = load_document(FIXTURES_DIR / "accord_teletravail.pdf")[0]["text"]
        self.assertIn("2026.\n\nArticle 1 : Bénéficiaires\nLe télétravail", text)
        self.assertIn("site.\n\nÀ titre exceptionnel", text)

    def test_ligatures_and_dot_leaders_are_cleaned(self):
        (self.dir / "toc.txt").write_text("Déﬁnition du télétravail ........... 11", encoding="utf-8")
        self.assertEqual(load_document(self.dir / "toc.txt")[0]["text"],
                         "Définition du télétravail ... 11")

    def test_bom_form_feed_and_nbsp_are_cleaned(self):
        (self.dir / "bom.txt").write_bytes("\ufeffAvec BOM.".encode("utf-8"))
        self.assertEqual(load_document(self.dir / "bom.txt")[0]["text"], "Avec BOM.")
        (self.dir / "ff.txt").write_text("Page1.\f\fPage2.\xa0\n\n \xa0\nFin.", encoding="utf-8")
        self.assertEqual(load_document(self.dir / "ff.txt")[0]["text"], "Page1.\n\nPage2.\n\nFin.")

    def test_justified_spaces_collapse_but_indentation_is_kept(self):
        (self.dir / "j.md").write_text("de  traçabilité,\t la   notion\n  - item", encoding="utf-8")
        self.assertEqual(load_document(self.dir / "j.md")[0]["text"],
                         "de traçabilité, la notion\n  - item")

    def test_text_inside_pdf_figures_is_read(self):
        pages, output = _quiet(load_document, FIXTURES_DIR / "form_xobject.pdf")
        self.assertEqual(output, "")
        self.assertIn("Texte normal.", pages[0]["text"])
        self.assertIn("Texte dans un Form XObject.", pages[0]["text"])

    def test_broken_page_does_not_cost_the_other_pages(self):
        pages, output = _quiet(load_document, FIXTURES_DIR / "broken_first_page.pdf")
        self.assertIn("cannot read page 1 of broken_first_page.pdf", output)
        self.assertEqual([(p["page"], p["text"]) for p in pages], [(3, "Page trois texte.")])

    def test_warning_names_the_page_that_failed(self):
        pages, output = _quiet(load_document, FIXTURES_DIR / "blank_then_broken_page.pdf")
        self.assertIn("cannot read page 3 of blank_then_broken_page.pdf", output)
        self.assertEqual([(p["page"], p["text"]) for p in pages], [(1, "Page un texte.")])

    def test_warnings_are_logged_not_printed(self):
        (self.dir / "empty.txt").write_text("", encoding="utf-8")
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            pages, output = _quiet(load_document, self.dir / "empty.txt")
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("empty.txt is empty", output)

    def test_corrupted_pdf_is_skipped_with_warning(self):
        (self.dir / "broken.pdf").write_bytes(b"not a pdf at all")
        pages, output = _quiet(load_document, self.dir / "broken.pdf")
        self.assertEqual(pages, [])
        self.assertIn("cannot read PDF broken.pdf", output)

    def test_pdf_without_text_is_skipped_with_warning(self):
        pages, output = _quiet(load_document, FIXTURES_DIR / "blank_scan.pdf")
        self.assertEqual(pages, [])
        self.assertIn("no extractable text", output)

    def test_password_protected_pdf_is_skipped_with_warning(self):
        pages, output = _quiet(load_document, FIXTURES_DIR / "password_protected.pdf")
        self.assertEqual(pages, [])
        self.assertIn("password-protected", output)

    def test_copy_protected_aes_pdf_is_read(self):
        # Common for HR documents: opens without a password, but copy and
        # print are restricted (owner password only, AES encryption).
        pages, output = _quiet(load_document, FIXTURES_DIR / "copy_protected_aes.pdf")
        self.assertEqual(output, "")
        self.assertEqual([p["page"] for p in pages], [1, 2])
        self.assertIn("Mutuelle Horizon", pages[0]["text"])

    def test_unsupported_empty_and_non_utf8_files(self):
        (self.dir / "photo.png").write_bytes(b"\x89PNG")
        (self.dir / "empty.txt").write_text("   \n\n ", encoding="utf-8")
        (self.dir / "latin1.txt").write_bytes("Congés payés".encode("latin-1"))
        for name, warning in (("photo.png", "unsupported file type"),
                              ("empty.txt", "is empty"), ("latin1.txt", "not valid UTF-8")):
            pages, output = _quiet(load_document, self.dir / name)
            self.assertEqual(pages, [], name)
            self.assertIn(warning, output, name)

    def test_directory_is_recursive_sorted_and_skips_hidden_files(self):
        (self.dir / "sub").mkdir()
        (self.dir / "sub" / "z.txt").write_text("Zed.", encoding="utf-8")
        (self.dir / "a.md").write_text("Aaa.", encoding="utf-8")
        (self.dir / ".hidden.txt").write_text("Secret.", encoding="utf-8")
        (self.dir / ".git").mkdir()
        (self.dir / ".git" / "x.txt").write_text("Git.", encoding="utf-8")
        pages, output = _quiet(load_directory, self.dir)
        self.assertEqual([p["source"] for p in pages], ["a.md", "sub/z.txt"])
        self.assertEqual(output, "")

    def test_missing_or_empty_directory_warns(self):
        pages, output = _quiet(load_directory, self.dir / "nope")
        self.assertEqual(pages, [])
        self.assertIn("is not a directory", output)
        pages, output = _quiet(load_directory, self.dir)
        self.assertEqual(pages, [])
        self.assertIn("no readable document", output)

    def test_corpus_documents_all_load(self):
        pages, output = _quiet(load_directory, DOCS_DIR)
        self.assertEqual(output, "")
        corpus = {"syd_accord_nao_2026.pdf", "loi_teletravail.md", "loi_conges_payes.md",
                  "loi_conge_mariage_pacs.md", "loi_conge_deces.md",
                  "loi_complementaire_sante.md", "loi_reglement_interieur.md",
                  "loi_jours_feries.txt"}
        self.assertLessEqual(corpus, {p["source"] for p in pages})

    def test_company_agreement_answers_hr_questions(self):
        pages = load_document(DOCS_DIR / "syd_accord_nao_2026.pdf")
        self.assertEqual(len(pages), 13)
        text = " ".join(" ".join(p["text"].split()) for p in pages)
        self.assertIn("jusqu’à 2 jours de télétravail/semaine", text)
        self.assertIn("à hauteur de 50%", text)
        self.assertFalse(any("\ue000" <= ch <= "\uf8ff" for ch in text))

SENTENCES = [f"Phrase numero {i} sur les conges payes de l'entreprise." for i in range(60)]
TEXT = "\n\n".join(" ".join(SENTENCES[i:i + 5]) for i in range(0, 60, 5))

class ChunkerTests(unittest.TestCase):

    def test_short_text_is_one_chunk(self):
        self.assertEqual(chunk_text("Un seul paragraphe court.", 100, 10),
                         ["Un seul paragraphe court."])

    def test_empty_text_gives_no_chunk(self):
        self.assertEqual(chunk_text("  \n\n  ", 100, 10), [])

    def test_no_chunk_exceeds_budget_and_none_is_empty(self):
        for size, overlap in ((40, 0), (40, 10), (100, 20), (500, 50)):
            chunks = chunk_text(TEXT, size, overlap)
            for chunk in chunks:
                self.assertTrue(chunk.strip())
                self.assertLessEqual(len(chunk), size * CHARS_PER_TOKEN)

    def test_overlap_repeats_end_of_previous_chunk(self):
        chunks = chunk_text(TEXT, 60, 15)
        self.assertGreater(len(chunks), 3)
        for previous, current in zip(chunks, chunks[1:]):
            shared = max(k for k in range(len(previous) + 1)
                         if current.startswith(previous[len(previous) - k:]))
            self.assertGreater(shared, 0, (previous, current))
            self.assertLess(shared, len(previous), (previous, current))

    def test_sentences_are_never_cut_when_they_fit(self):
        chunks = chunk_text(TEXT, 60, 0)
        for chunk in chunks:
            for line in chunk.split("\n\n"):
                self.assertTrue(line.endswith("."), chunk)
        joined = "\n".join(chunks)
        for sentence in SENTENCES:
            self.assertIn(sentence, joined)

    def test_pdf_style_line_wraps_do_not_cut_sentences(self):
        text = "\n".join(
            "Le salarie peut teletravailler deux jours\npar semaine apres trois mois." for _ in range(20)
        )
        for chunk in chunk_text(text, 50, 0):
            self.assertTrue(chunk.endswith("mois."), chunk)

    def test_oversized_word_is_hard_cut(self):
        chunks = chunk_text("x" * 1000, 50, 0)
        self.assertEqual("".join(chunks), "x" * 1000)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 50 * CHARS_PER_TOKEN)

    def test_section_numbers_and_abbreviations_are_not_sentence_ends(self):
        text = ("Il reste 32 euros a payer chaque mois. 2. Dispenses\n"
                "Voir M. Dupont, art. 3 et p. 4 du contrat de travail.")
        sentences = [piece for _, piece in _pieces(text, _LEVELS[1])]
        self.assertEqual(sentences, [
            "Il reste 32 euros a payer chaque mois.",
            "2. Dispenses\nVoir M. Dupont, art. 3 et p. 4 du contrat de travail.",
        ])

    def test_list_items_keep_their_line_breaks(self):
        items = "\n".join(f"- Cas numero {i} : {i} jours ouvres." for i in range(30))
        for chunk in chunk_text(items, 60, 0):
            for line in chunk.split("\n"):
                self.assertTrue(line.startswith("- Cas numero"), chunk)

    def test_heading_stays_with_its_body(self):
        body = " ".join(SENTENCES[:4])
        text = f"{body}\n\n4. Absence pour maladie\n\n{body}"
        chunks = chunk_text(text, 70, 0)
        self.assertFalse(any(c.endswith("Absence pour maladie") for c in chunks), chunks)
        self.assertTrue(any(c.startswith("4. Absence pour maladie\n\n") for c in chunks), chunks)

    def test_heading_before_oversized_paragraph_stays_with_it(self):
        intro = " ".join(SENTENCES[:4])
        body = " ".join(SENTENCES[10:20])
        chunks = chunk_text(f"{intro}\n\n## Article 6 : Sanctions\n\n{body}", 70, 0)
        self.assertFalse(any(c.endswith("Sanctions") for c in chunks), chunks)
        self.assertTrue(any(c.startswith("## Article 6 : Sanctions\n\n") for c in chunks), chunks)

    def test_short_heading_before_long_paragraph_is_not_a_chunk_alone(self):
        text = "Article 1.\n\n" + "Le salarie beneficie de conges payes chaque annee. " * 60
        chunks = chunk_text(text, 120, 20)
        self.assertTrue(chunks[0].startswith("Article 1."), chunks[0])
        self.assertGreater(len(chunks[0]), 100)

    def test_leftover_of_exactly_a_quarter_is_not_carried(self):
        # Boundary of the "small leftover" rule: strictly less than
        # max_chars // CARRY_DIVISOR is carried, exactly that is not.
        short = "abcdefghijklm."
        long_paragraph = " ".join(["mot"] * 40)
        self.assertEqual(len(short), 59 // 4)
        chunks = _split(f"{short}\n\n{long_paragraph}", 59)
        self.assertEqual(chunks[0], short)

    def test_captured_warnings_survive_a_stricter_root_level(self):
        root = logging.getLogger()
        previous = root.level
        root.setLevel(logging.ERROR)
        try:
            pages, output = _quiet(load_document, "photo.png")
        finally:
            root.setLevel(previous)
        self.assertIn("unsupported file type", output)

    def test_invalid_config_raises(self):
        for size, overlap in ((0, 0), (50, 50), (50, -1)):
            with self.assertRaises(ValueError):
                chunk_text("texte", size, overlap)

    def test_chunk_pages_keeps_source_page_and_index(self):
        pages = [
            {"source": "a.pdf", "page": 1, "text": TEXT},
            {"source": "a.pdf", "page": 2, "text": "Page deux."},
            {"source": "b.txt", "page": None, "text": "Autre document."},
        ]
        chunks = chunk_pages(pages, 60, 10)
        a_chunks = [c for c in chunks if c["source"] == "a.pdf"]
        self.assertEqual([c["chunk_index"] for c in a_chunks], list(range(len(a_chunks))))
        self.assertEqual(a_chunks[-1], {"source": "a.pdf", "page": 2,
                                        "chunk_index": len(a_chunks) - 1, "text": "Page deux."})
        self.assertEqual(chunks[-1], {"source": "b.txt", "page": None,
                                      "chunk_index": 0, "text": "Autre document."})

    def test_corpus_documents_chunk_within_budget(self):
        pages, _ = _quiet(load_directory, DOCS_DIR)
        chunks = chunk_pages(pages, 500, 50)
        self.assertGreaterEqual(len(chunks), len(pages))
        for chunk in chunks:
            self.assertLessEqual(len(chunk["text"]), 500 * CHARS_PER_TOKEN)

if __name__ == "__main__":
    unittest.main()
