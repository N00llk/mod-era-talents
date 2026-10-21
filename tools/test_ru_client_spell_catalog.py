"""Guard recovered Russian spell text against the defects in the legacy JSON.

These checks need only source catalogs. Binary smoke verification can be run
separately with the user's original client DBCs; no client data is redistributed.
"""
import collections
import re

import pytest

import build_client_patch as P
import client_spell_locales as L

# Include named references and whole arithmetic expressions, so their indices,
# constants and macro names aren't mistaken for rank-dependent prose values.
DBC_REFERENCE = re.compile(r"\$\{[^}]*\}|\$<[^>]+>|\$(?:\d+)?(?:@[A-Za-z]+\d*|[A-Za-z]\d*|[?:;])")


def literal_numbers(text):
    return collections.Counter(re.findall(r"\d+(?:\.\d+)?", DBC_REFERENCE.sub("", text)))


@pytest.fixture(scope="module")
def catalogs():
    paths = P.datasets()
    english_common, english = L.catalogs(paths, "enUS")
    common, russian = L.catalogs(paths, "ruRU")
    return english, russian, common


def test_ru_catalog_complete_and_rank_format_localized(catalogs):
    english, russian, common = catalogs
    assert russian.keys() == english.keys()
    assert common["rank"] % 3 == "Ранг 3"


@pytest.mark.parametrize("rel", [p.relative_to(P.ROOT / "era-data") for p in P.datasets()])
def test_russian_text_preserves_references_and_magnitudes(catalogs, rel):
    english, russian, _ = catalogs
    entries = L.load(L.DEFAULT_ROOT / "enUS" / rel)["texts"]
    for key in entries:
        for field, source in english[key].items():
            translated = russian[key][field]
            where = f"{rel}: {key}.{field}"
            assert sorted(DBC_REFERENCE.findall(translated)) == sorted(DBC_REFERENCE.findall(source)), where
            assert literal_numbers(translated) == literal_numbers(source), where
            prose = DBC_REFERENCE.sub("", translated)
            assert not re.search(r"[A-Za-z]{3,}|<[^>]+>|\[S\d+", prose), where
            if translated:
                assert re.search("[А-Яа-яЁё]", prose), where


def test_magic_absorption_uses_each_current_rank_without_extra_cooldown(catalogs):
    _, russian, _ = catalogs
    for rank, sid in enumerate(range(932326, 932331), 1):
        text = russian[f"spell.{sid}"]["description"]
        assert f"на {rank * 2} ед." in text
        assert f"восстанавливает {rank}%" in text
        assert "Время восстановления" not in text


def test_cold_snap_and_sanctity_aura_do_not_use_unrelated_donor_text(catalogs):
    _, russian, _ = catalogs
    cold_snap = russian["spell.932335"]
    assert cold_snap["name"] == "Холодная хватка"
    assert "восстановление всех ваших заклинаний магии льда" in cold_snap["description"]
    assert "ледяной глыбы" not in cold_snap["description"].lower()
    sanctity = russian["spell.932602"]
    assert sanctity["name"] == "Аура святости"
    assert "урон от светлой магии" in sanctity["description"]
    assert "брон" not in sanctity["description"]


def test_dynamic_spell_damage_is_not_replaced_with_legacy_static_numbers(catalogs):
    english, russian, _ = catalogs
    pyro = russian["spell.932310"]["description"]
    assert all(token in pyro for token in ("$s1", "$o2", "$d"))
    mangle_key = next(key for key, entry in english.items() if entry["name"] == "Mangle (Cat)")
    mangle = russian[mangle_key]["description"]
    assert "${$m1*$m3/100}" in mangle
