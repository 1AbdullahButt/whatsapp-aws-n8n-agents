"""Rule-based classifier: which trade, and is it urgent?

All rules are plain word lists so they are easy to read and change.
Categories are checked in the order below and the first match wins.
Heating comes before plumbing so "no hot water" goes to heating.
"""
import re
from dataclasses import dataclass

CATEGORY_KEYWORDS = {
    "heating": ["boiler", "heating", "radiator", "heater", "hot water", "gas", "thermostat"],
    "electrical": ["power", "socket", "light", "lights", "fuse", "electric", "electricity",
                   "sparks", "wiring", "outlet", "switch"],
    "plumbing": ["leak", "leaking", "pipe", "toilet", "sink", "drain", "tap", "water",
                 "flood", "flooding", "shower", "blocked"],
    "locks": ["lock", "locked", "locked out", "lockout", "key", "keys", "door"],
    "pests": ["mice", "mouse", "rat", "rats", "cockroach", "cockroaches", "bed bugs",
              "pest", "pests", "ants", "wasps"],
}

# Phrases that are always urgent.
URGENT_PHRASES = ["gas smell", "smell gas", "smell of gas", "flooding", "flood",
                  "fire", "smoke", "sparks", "locked out", "lockout"]

# Phrases that are urgent only in the cold months.
WINTER_URGENT_PHRASES = ["no heating", "no heat"]
WINTER_MONTHS = {11, 12, 1, 2}  # November to February


@dataclass
class Classification:
    category: str
    urgent: bool
    reason: str


def classify(text, month):
    """Classify a tenant message. `month` is 1-12, passed in so tests can pick it."""
    lowered = text.lower()
    category = _find_category(lowered)
    urgent, reason = _check_urgent(lowered, month)
    return Classification(category=category, urgent=urgent, reason=reason)


def _contains(text, phrase):
    """True if the phrase appears as whole words (so "rat" does not match "rather")."""
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


def _find_category(text):
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if _contains(text, keyword):
                return category
    return "other"


def _check_urgent(text, month):
    for phrase in URGENT_PHRASES:
        if _contains(text, phrase):
            return True, f"matched urgent phrase '{phrase}'"
    for phrase in WINTER_URGENT_PHRASES:
        if _contains(text, phrase):
            if month in WINTER_MONTHS:
                return True, f"matched '{phrase}' in a winter month"
            return False, f"matched '{phrase}' but not a winter month"
    return False, "no urgent phrase found"
