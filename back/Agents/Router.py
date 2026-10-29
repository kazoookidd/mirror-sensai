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


_DATE_QUESTION = re.compile(
    r"\b(?:on est quel jour|quel jour (?:sommes-nous|on est|est-on|est-ce)|c'est quel jour|"
    r"quelle (?:est la )?date (?:sommes-nous|on est|est-on|aujourd'hui)|quelle est la date|"
    r"(?:la )?date d'aujourd'hui|on est le combien|"
    r"what day is (?:it|today)|what(?:'s| is) (?:the )?date|today's date)\b",
    re.IGNORECASE,
)


def asks_for_date(text: str) -> bool:
    """"On est quel jour ?": the date is in the system prompt, no tool is needed (a 1B model
    would search the web for "jour" and answer from the results)."""
    return _DATE_QUESTION.search(text) is not None


# "Poser" is only said of leave: a date is enough ("je pose lundi").
_FILE_LEAVE = re.compile(
    r"\b(?:je|j') ?(?:pose|d[ée]pose|(?:veux|voudrais|souhaite|aimerais|vais|dois) (?:poser|d[ée]poser))\b"
    r"|\bpose[sz]?[- ]moi\b|\bi(?:'m| am| want to| would like to|'d like to)? (?:book|booking)\b",
    re.IGNORECASE,
)
_WHEN = re.compile(
    r"\b(?:cong[ée]s?|vacances|rtt|repos|jours?|semaines?|demi-journ[ée]e|lundi|mardi|mercredi|jeudi|vendredi|"
    r"samedi|dimanche|demain|du \d|le \d|days?|leave|holidays?|vacation|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|tomorrow)\b",
    re.IGNORECASE,
)
# "Prendre" is said of anything ("je prends le train demain"): a word of leave is needed.
_TAKE = re.compile(
    r"\b(?:je|j') ?(?:prends|(?:veux|voudrais|souhaite|aimerais|vais|dois) prendre)\b"
    r"|\bi(?:'m| am| want to| would like to|'d like to)? (?:take|taking)\b",
    re.IGNORECASE,
)
_LEAVE_WORD = re.compile(
    r"\b(?:cong[ée]s?|vacances|rtt|repos|demi-journ[ée]e|journ[ée]e off|off|leave|holidays?|vacation)\b",
    re.IGNORECASE,
)


# "Annule mon congé du 3 novembre", "cancel my leave on Monday"
_CANCEL = re.compile(r"\b(?:annule[rz]?|supprime[rz]?|retire[rz]?|cancel(?:led|ling)?)\b", re.IGNORECASE)
_REQUEST_WORD = re.compile(r"\b(?:cong[ée]s?|vacances|rtt|demandes?|absences?|leave|holidays?|vacation|day off)\b",
                           re.IGNORECASE)
# "Comment annuler un congé ?" asks about the rules: it keeps the HR excerpts.
_QUESTION = re.compile(r"^\W*(?:comment|est-ce|peut-on|puis-je|pourquoi|quand|how|can i|why|when)\b", re.IGNORECASE)


def asks_for_leave(text: str) -> bool:
    """"Je pose du 3 au 7 novembre", "annule mon congé du 3": the user files or cancels a leave
    request, the agent must act. HR excerpts about leave rules would only distract a small model
    into explaining the rules (measured: qwen2.5:3b calls the tool 3/3 times without them, 0/3 with them)."""
    return bool((_FILE_LEAVE.search(text) and _WHEN.search(text))
                or (_TAKE.search(text) and _LEAVE_WORD.search(text))
                or (_CANCEL.search(text) and _REQUEST_WORD.search(text) and not _QUESTION.search(text)))


def should_offer_tools(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    return _SMALL_TALK.match(text) is None and not asks_for_date(text)


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
