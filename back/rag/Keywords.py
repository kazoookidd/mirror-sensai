"""
[R2] Keyword relevance (BM25) of the indexed chunks, to rerank what the embeddings found.

Embeddings catch the meaning; exact terms ("Pacs", "RTT", a year) can score lower than a
loosely related passage. BM25 rewards the rare words of the question found in a chunk.
Accents and case are ignored, and the most common French and English words are skipped.
"""

import math
import re
import unicodedata
import numpy as np

K1 = 1.5
B = 0.75
STOP_WORDS = frozenset("""
a ai as au aux avec ce ces cette d de des du elle elles en est et il ils j je l la le les leur leurs
ma me mes mon n ne nous on ou par pas plus pour qu que quel quelle quelles quels qui quoi s sa se ses
son sont sur t ta te tes ton tu un une vos votre vous y combien comment dans etre avoir faut peut
the of to and in is are for on with what how which who do does can i my me it be at an or this that
""".split())


def tokens(text: str) -> list[str]:
    """Words of `text`, without accents, case or stop words."""
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return [word for word in re.findall(r"[a-z0-9]+", plain) if word not in STOP_WORDS]


def bm25_scores(question: str, texts: list[str]) -> np.ndarray:
    """BM25 score of each text for `question` (0 when no word of the question is in it)."""
    documents = [tokens(text) for text in texts]
    scores = np.zeros(len(documents))
    if not documents:
        return scores
    average = sum(len(words) for words in documents) / len(documents) or 1
    frequency = {}
    for words in documents:
        for word in set(words):
            frequency[word] = frequency.get(word, 0) + 1
    for word in set(tokens(question)):
        if word not in frequency:
            continue
        idf = math.log(1 + (len(documents) - frequency[word] + 0.5) / (frequency[word] + 0.5))
        for i, words in enumerate(documents):
            count = words.count(word)
            if count:
                scores[i] += idf * count * (K1 + 1) / (count + K1 * (1 - B + B * len(words) / average))
    return scores
