"""The coin-ceiling taunt pool: hand-written lines, loaded from data_files."""
import taunts


def test_pool_is_loaded_and_nonempty():
    pool = taunts._load()
    assert len(pool) >= 20
    assert taunts._FALLBACK not in pool  # the real file was found, not the fallback


def test_lines_are_clean_one_liners():
    for line in taunts._load():
        assert line.strip() == line
        assert "\n" not in line
        assert not line.startswith("#")
        assert 10 < len(line) < 300


def test_taunts_stay_off_families():
    # House rule: crude about the player, never about anyone's family.
    banned = ("mom", "mother", "dad", "father", "parent", "sister",
              "brother", "wife", "husband", "kids", "children", "family")
    for line in taunts._load():
        lowered = line.lower()
        for word in banned:
            assert word not in lowered, f"family reference in taunt: {line}"


def test_ceiling_taunt_returns_a_pool_line():
    assert taunts.ceiling_taunt() in taunts._load()
