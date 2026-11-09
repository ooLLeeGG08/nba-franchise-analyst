"""Player-name matching across sources (contracts, nba_api rosters, Basketball-Reference).

Each source spells some names differently ("Herb Jones" vs "Herbert Jones",
"Nikola Jokić" vs "Nikola Jokic"), so every name goes through name_key()
before two sources are joined.
"""
import re
import unicodedata

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

# Same player, different spelling between sources: key -> canonical key.
ALIASES = {
    "herb jones": "herbert jones",
    "nahshon hyland": "bones hyland",
    "ron holland": "ronald holland",
    "nic claxton": "nicolas claxton",
    "bogolijub markovic": "bogoljub markovic",
    "pelle larson": "pelle larsson",
    "emanuel sharpe": "emanuel sharp",
    "sviatoslav mykhailiuk": "svi mykhailiuk",
}


def name_key(name):
    """Lowercase, no accents/punctuation/suffixes: "Jaren Jackson Jr." -> "jaren jackson"."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = text.replace(".", "").replace("-", " ")  # "R.J." -> "rj", "Gilgeous-Alexander" -> two words
    text = re.sub(r"[^a-z ]", "", text)
    words = [w for w in text.split() if w not in _SUFFIXES]
    key = " ".join(words)
    return ALIASES.get(key, key)


def slug(name):
    return name_key(name).replace(" ", "-")
