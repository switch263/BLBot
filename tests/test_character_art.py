"""The per-user character portrait: valid PNG, and seed-bound determinism."""
import io

import pytest


def _render():
    pytest.importorskip("PIL")  # Pillow is a prod dep; may be absent locally
    from character_art import render_character_image
    return render_character_image


def test_render_produces_a_png():
    render = _render()
    buf = render("Tester", seed=123)
    assert isinstance(buf, io.BytesIO)
    data = buf.read()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) > 5_000


def test_same_seed_is_byte_identical():
    # This is the whole premise: a seed binds a user to one and only one card.
    render = _render()
    a = render("Tester", seed=123).read()
    b = render("Tester", seed=123).read()
    assert a == b


def test_different_seeds_differ():
    render = _render()
    a = render("Tester", seed=123).read()
    b = render("Tester", seed=999).read()
    assert a != b


def test_survives_odd_input():
    # A Discord command must never get a stack trace back; any input still
    # yields a valid PNG.
    render = _render()
    for name in ("", "   ", "x" * 500, "💀🎰🔥 ваня", "a\nb\tc"):
        assert render(name, seed=7).read().startswith(b"\x89PNG")


def test_catalog_is_well_stocked():
    # The class/epithet pools are the character's identity; keep them rich.
    pytest.importorskip("PIL")
    import character_art
    assert len(character_art._CLASSES) >= 20
    assert len(character_art._TITLES) >= 20
