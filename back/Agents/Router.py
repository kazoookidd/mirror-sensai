"""
Decides, BEFORE any model call, whether the tools are worth offering for a
message. Cheap and deterministic: the goal is only to keep trivial messages
(greetings, thanks, "ok") out of the tool loop. For everything else the model
itself decides, guided by the tool guidance in its system prompt, and a
message that needs no tool still costs exactly one model call.
"""

import re

_SMALL_TALK = re.compile(
    r"^\W*(?:"
    r"bonjour|bonsoir|salut|coucou|hello|hi|hey|yo|"
    r"merci(?: beaucoup)?|thanks?|thank you|"
    r"ok(?:ay)?|d'accord|dac|super|parfait|top|cool|génial|"
    r"oui|non|yes|no|"
    r"ça va|comment ça va|how are you|"
    r"au revoir|à bientôt|bye|bonne journée|bonne soirée"
    r")(?:\W+(?:à tous|tout le monde|sensai|!+|\.+))*\W*$",
    re.IGNORECASE,
)


def should_offer_tools(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    return _SMALL_TALK.match(text) is None


_SEARCH_REQUEST = re.compile(
    r"\b(?:fais|fait|faire|faites|effectue[rz]?|lance[rz]?)\s+(?:des\s+|une\s+|la\s+)?recherches?\b"
    r"|\bcherche[rz]?\b|\brecherche[rz]?\s+(?:sur|les|des|moi)\b"
    r"|\bsur (?:internet|le web|le net)\b|\bon the (?:web|internet)\b|\bonline\b"
    r"|\bsearch\b|\blook (?:it )?up\b|\bgoogle\b",
    re.IGNORECASE,
)


def asks_for_search(text: str) -> bool:
    """The user explicitly asks to look something up ("fais des recherches",
    "search the web"). Small models then need a nudge to actually call the tool."""
    return _SEARCH_REQUEST.search(text) is not None


_ATTACHMENT_REFERENCE = re.compile(
    r"\b(?:fichiers?|documents?|pdf|contrats?|textes?|pi[eè]ces?\s+jointes?)\s+(?:joints?|ci-joints?|attach[ée]s?|envoy[ée]s?)\b"
    r"|\b(?:ce|cet|cette|ces|le|la|les|mon|ma|mes)\s+(?:fichiers?|documents?|pdf|pi[eè]ces?\s+jointes?)\b"
    r"|\battached\s+(?:files?|documents?)\b|\bth(?:is|e|ese)\s+(?:files?|documents?|pdf)\b",
    re.IGNORECASE,
)


def refers_to_attachments(text: str) -> bool:
    """The user talks about "the file", "ce document", "le contrat joint". When the chat has joined
    files, their text is already in the context: small models would otherwise try to open them with a tool."""
    return _ATTACHMENT_REFERENCE.search(text) is not None
