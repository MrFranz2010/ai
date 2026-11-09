"""Ricerca con classifica sugli appunti di NOKK.

Nessun servizio esterno: le parole vengono normalizzate (minuscole, accenti),
private delle parole vuote italiane e confrontate per prefisso, così «scadenz»
trova «scadenza» e «compit» trova «compiti». Il punteggio premia quante parole
della ricerca compaiono e quante volte, più un bonus per la frase intera.
"""

import re
import unicodedata

STOPWORDS = frozenset({
    "a", "ad", "al", "alla", "alle", "allo", "anche", "che", "chi", "ci",
    "come", "con", "da", "dal", "dalla", "delle", "dei", "del", "di", "e",
    "ed", "gli", "ha", "ho", "i", "il", "in", "io", "la", "le", "lo", "ma",
    "mi", "ne", "nel", "nella", "no", "non", "o", "per", "più", "può", "qual",
    "quale", "se", "sei", "si", "sono", "su", "sul", "sulla", "te", "ti",
    "tra", "tu", "un", "una", "uno", "vi", "voi", "è", "era", "essere",
})

# Suffissi frequenti: bastano a far combaciare singolare e plurale.
SUFFIXES = (
    "azioni", "azione", "zioni", "zione", "mente", "ità", "isti", "ista",
    "ismi", "ismo", "aggi", "aggio", "etti", "etto", "ini", "ino", "oni",
    "one", "ali", "ale", "ari", "ario", "ivi", "ivo", "ati", "ato", "iti",
    "ito", "uti", "uto", "che", "chi", "i", "e", "a", "o",
)

WORD_PATTERN = re.compile(r"[a-z0-9]+")
MAX_DOCUMENT_TEXT = 1200


def normalize(text):
    if not isinstance(text, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokens(text):
    return [
        word for word in WORD_PATTERN.findall(normalize(text))
        if len(word) > 1 and word not in STOPWORDS
    ]


def stem(word):
    for suffix in SUFFIXES:
        if len(word) - len(suffix) >= 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def make_document(kind, identifier, title, text, extra=None):
    title = (title or "").strip()
    text = (text or "").strip()
    document = {
        "kind": kind,
        "id": str(identifier or ""),
        "title": title[:160] or "(senza titolo)",
        "text": text[:MAX_DOCUMENT_TEXT],
    }
    if extra:
        document.update(extra)
    return document


def excerpt(text, query_tokens, length=150):
    """Short window of the text around the first useful word."""
    flat = " ".join((text or "").split())
    if not flat:
        return ""
    lowered = normalize(flat)
    position = -1
    for token in query_tokens:
        index = lowered.find(stem(token))
        if index != -1 and (position == -1 or index < position):
            position = index
    if position <= 0:
        return flat[:length] + ("…" if len(flat) > length else "")
    start = max(0, position - length // 3)
    piece = flat[start:start + length]
    if start > 0:
        piece = "…" + piece
    if start + length < len(flat):
        piece = piece + "…"
    return piece


def score_document(query_tokens, phrase, document):
    haystack = normalize(f"{document['title']} {document['text']}")
    words = [stem(word) for word in WORD_PATTERN.findall(haystack)]
    if not words:
        return 0.0
    stems = [stem(token) for token in query_tokens]
    matched = 0
    occurrences = 0
    for token in stems:
        hits = sum(
            1 for word in words
            if word == token or (len(token) >= 3 and word.startswith(token))
            or (len(word) >= 3 and token.startswith(word))
        )
        if hits:
            matched += 1
            occurrences += hits
    if not matched:
        return 0.0
    coverage = matched / len(stems)
    title_hits = sum(1 for token in stems if token in normalize(document["title"]))
    score = coverage * 70 + min(occurrences, 8) * 3 + title_hits * 6
    if phrase and len(phrase) >= 4 and normalize(phrase) in haystack:
        score += 25
    return round(score, 2)


def rank_documents(query, documents, limit=8):
    query_tokens = tokens(query)
    if not query_tokens:
        return []
    phrase = " ".join(query.split())
    results = []
    for document in documents:
        score = score_document(query_tokens, phrase, document)
        if not score:
            continue
        results.append({
            **document,
            "score": score,
            "snippet": excerpt(document["text"] or document["title"], query_tokens),
        })
    results.sort(key=lambda item: (-item["score"], item["title"].casefold()))
    return results[:limit]
