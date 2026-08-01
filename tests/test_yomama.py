"""The your-mother catalog: combo floor, line hygiene, assembly, rendering."""
import random

import pytest

import yomama


# --- catalog data ----------------------------------------------------------

def test_catalog_clears_the_thousand_combo_floor():
    # The whole premise of the cog. Losing this means the joke pool got thin.
    assert yomama.combo_count() >= 1000


def test_every_category_is_stocked():
    assert len(yomama.CATEGORIES) >= 8
    for name, cat in yomama.CATEGORIES.items():
        assert name == name.lower() and " " not in name
        assert len(cat["setups"]) >= 4, f"{name} has too few setups"
        assert len(cat["punchlines"]) >= 15, f"{name} has too few punchlines"


def test_setups_are_bare_clauses():
    # The joke is assembled as "{setup}, {punchline}" — a setup that already
    # carries punctuation produces "so fat., she..." nonsense.
    for name, cat in yomama.CATEGORIES.items():
        for setup in cat["setups"]:
            assert setup.strip() == setup
            assert not setup.endswith((".", ",", "!", "?")), f"{name}: {setup}"
            assert 10 < len(setup) < 60


def test_punchlines_are_finished_sentences():
    for name, cat in yomama.CATEGORIES.items():
        for line in cat["punchlines"]:
            assert line.strip() == line
            # A quoted punchline legitimately ends "...please.'" — check the
            # terminator, not the last character.
            assert line.rstrip("'\"").endswith((".", "!", "?")), f"{name}: {line}"
            assert 10 < len(line) < 200
            assert "\n" not in line


def test_no_duplicate_punchlines_anywhere():
    seen = [line for cat in yomama.CATEGORIES.values() for line in cat["punchlines"]]
    dupes = {line for line in seen if seen.count(line) > 1}
    assert not dupes, f"duplicate punchlines: {dupes}"


def test_no_placeholders_left_in_the_data():
    # These lines are complete jokes, not mad-lib templates.
    for cat in yomama.CATEGORIES.values():
        for line in cat["setups"] + cat["punchlines"]:
            assert "{" not in line and "}" not in line


# --- assembly --------------------------------------------------------------

def test_joke_pairs_a_setup_with_a_punchline():
    for _ in range(200):
        text = yomama.joke()
        setup, _, punch = text.partition(", ")
        cat = next(c for c in yomama.CATEGORIES.values() if setup in c["setups"])
        assert punch in cat["punchlines"], f"crossed categories: {text}"


def test_joke_honors_a_requested_category():
    cat = yomama.CATEGORIES["fat"]
    for _ in range(50):
        setup, _, punch = yomama.joke("fat").partition(", ")
        assert setup in cat["setups"]
        assert punch in cat["punchlines"]


def test_unknown_category_falls_back_instead_of_raising():
    # The caller is a Discord command; a bad key is not worth a stack trace.
    assert yomama.joke("nonexistent-category")


def test_seeded_rng_is_reproducible():
    a = yomama.joke(rng=random.Random(7))
    b = yomama.joke(rng=random.Random(7))
    assert a == b


def test_category_names_match_the_catalog():
    assert yomama.category_names() == list(yomama.CATEGORIES)


# --- the illustration ------------------------------------------------------

def test_render_produces_a_png():
    pytest.importorskip("PIL")  # Pillow is a prod dep; may be absent locally
    from yomama_art import render_joke_image

    buf = render_joke_image(yomama.joke(), seed=1234)
    data = buf.read()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 5_000


def test_render_survives_a_very_long_joke():
    pytest.importorskip("PIL")
    from yomama_art import render_joke_image

    long_joke = "Your mother is so fat, " + "she keeps going and going " * 20 + "."
    assert render_joke_image(long_joke, seed=1).read().startswith(b"\x89PNG")
