import pytest

from app.classifier import classify


@pytest.mark.parametrize("text, category", [
    ("My kitchen sink is leaking", "plumbing"),
    ("The toilet is blocked", "plumbing"),
    ("No power in the bedroom socket", "electrical"),
    ("The boiler is broken", "heating"),
    ("No hot water since Monday", "heating"),
    ("The front door lock is stuck", "locks"),
    ("I think we have mice in the kitchen", "pests"),
    ("The window blind fell off", "other"),
])
def test_categories(text, category):
    assert classify(text, month=6).category == category


def test_gas_smell_is_urgent():
    result = classify("I can smell gas in the kitchen", month=6)
    assert result.urgent
    assert "smell gas" in result.reason


@pytest.mark.parametrize("text", ["The bathroom is flooding", "There are sparks from the socket",
                                  "I am locked out", "Smoke coming from the oven"])
def test_always_urgent_phrases(text):
    assert classify(text, month=7).urgent


def test_no_heating_urgent_only_in_winter():
    assert classify("We have no heating", month=12).urgent
    assert classify("We have no heating", month=2).urgent
    assert not classify("We have no heating", month=7).urgent


def test_whole_words_only():
    # "rather" must not match the pest keyword "rat".
    assert classify("I would rather not wait", month=6).category == "other"
