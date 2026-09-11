"""The taunt pools: hand-written lines, loaded from data_files."""
import pytest

import taunts

POOLS = list(taunts._POOLS)


@pytest.mark.parametrize("pool", POOLS)
def test_pool_is_loaded_and_nonempty(pool):
    lines = taunts._load(pool)
    assert len(lines) >= 20
    assert taunts._POOLS[pool][1] not in lines  # the real file was found, not the fallback


@pytest.mark.parametrize("pool", POOLS)
def test_lines_are_clean_one_liners(pool):
    for line in taunts._load(pool):
        assert line.strip() == line
        assert "\n" not in line
        assert not line.startswith("#")
        assert 10 < len(line) < 300


@pytest.mark.parametrize("pool", POOLS)
def test_taunts_stay_off_families(pool):
    # House rule: crude about the player, never about anyone's family.
    banned = ("mom", "mother", "dad", "father", "parent", "sister",
              "brother", "wife", "husband", "kids", "children", "family")
    for line in taunts._load(pool):
        lowered = line.lower()
        for word in banned:
            assert word not in lowered, f"family reference in taunt: {line}"


def test_pickers_return_pool_lines():
    assert taunts.ceiling_taunt() in taunts._load("ceiling")
    assert taunts.broke_taunt() in taunts._load("broke")
