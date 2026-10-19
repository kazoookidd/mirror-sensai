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
