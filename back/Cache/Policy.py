"""
What may be served from the cache, and what may be stored in it. Deliberately
simple, readable rules: when in doubt the answer is "no" and the model is asked.

Serving (the NEW question must be self-contained):
  - not too short, no reference to the conversation ("and for tomorrow?", "that one")
  - not time-sensitive ("today", "latest", "news"...): the answer would go stale
  - not an explicit request to search the web

Storing (the ANSWER must be reusable):
  - the question passes the rules above
  - produced by the model alone: no tool was used (web results age)
  - not empty or tiny, not a refusal ("I cannot search...") that would poison later turns
  - produced with no earlier conversation behind it (CACHE_CONTEXT_FREE_ONLY); small talk
    ("hello", "ok", "merci") is not a conversation in that sense
"""

import re

from Agents.Router import asks_for_date, asks_for_leave, asks_for_search

MIN_WORDS = 3
MIN_CHARS = 12
MIN_ANSWER_CHARS = 20

_CONNECTORS = {"et", "mais", "donc", "alors", "ok", "oui", "non", "aussi", "pourquoi",
               "and", "but", "so", "also", "why", "then", "ensuite", "sinon"}

_REFERS_TO_CONVERSATION = re.compile(
    r"\b(ça|cela|ceci|celui|celle|ceux|ci-dessus|ci-dessous|précédent|précédente|plus haut|"
    r"that|this|it|above|below|previous|same|the former|the latter)\b", re.IGNORECASE)

_TIME_SENSITIVE = re.compile(
    r"\b(aujourd'hui|aujourdhui|demain|hier|maintenant|actuel|actuelle|actuels|actuellement|"
    r"dernier|dernière|derniers|dernières|récent|récente|récemment|ce soir|cette semaine|"
    r"ce mois|cette année|en ce moment|prochain|prochaine|"
    r"today|tomorrow|yesterday|now|current|currently|latest|recent|recently|tonight|"
    r"this week|this month|this year|right now|next|"
    r"actualité|actualités|news|météo|weather|score|prix|price|cours de|"
    r"quel jour|quelle date|quelle heure|quel mois|quelle année|on est quel|sommes-nous|"
    r"what day|what date|what time|what year|what month)\b", re.IGNORECASE)

_REFUSAL = re.compile(
    r"(je n'ai pas (la capacité|accès|d'informations récentes)|je ne peux pas (faire|effectuer|accéder)|"
    r"en tant qu'assistant textuel|i (cannot|can't|am unable to|do not have the ability)|"
    r"as a text-based|i don't have access|"
    r"refused:|does not give that information|tries to drop the assistant's rules)", re.IGNORECASE)


def question_is_self_contained(text: str) -> bool:
    text = text.strip()
    words = re.findall(r"\w+", text.lower())
    if len(text) < MIN_CHARS or len(words) < MIN_WORDS:
        return False
    if words[0] in _CONNECTORS:
        return False
    return _REFERS_TO_CONVERSATION.search(text) is None


def has_substantive_history(history: list[dict]) -> bool:
    """Does the conversation so far contain a real question the next answer could lean on?
    Greetings, "ok", "merci" or "1 + 1" do not count: they cannot change an answer."""
    from Agents.Router import should_offer_tools
    for message in history:
        if message.get("role") != "user":
            continue
        text = message.get("content", "").strip()
        words = re.findall(r"\w+", text)
        if len(text) >= MIN_CHARS and len(words) >= MIN_WORDS and should_offer_tools(text):
            return True
    return False


def question_is_time_sensitive(text: str) -> bool:
    return _TIME_SENSITIVE.search(text) is not None or asks_for_search(text) or asks_for_date(text)


def may_serve(question: str) -> bool:
    # Filing or cancelling a leave is an action: its right answer is a tool call, never a stored text.
    return (question_is_self_contained(question) and not question_is_time_sensitive(question)
            and not asks_for_leave(question))


def may_store(question: str, answer: str, *, used_tools: bool, had_history: bool,
              context_free_only: bool = True) -> bool:
    if used_tools or not may_serve(question):
        return False
    if context_free_only and had_history:
        return False
    answer = answer.strip()
    return len(answer) >= MIN_ANSWER_CHARS and _REFUSAL.search(answer) is None
