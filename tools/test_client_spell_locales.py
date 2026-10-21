"""Binary locale layout, catalog completeness and source-preserving patch generation."""
import json
import io
import pathlib
import struct
import zipfile

import pytest
import yaml

import build_client_dbc as B
import build_client_patch as P
import build_client_skilllineability as S
import client_spell_locales as L
import gen_era_talents as G


def write_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_dbc(path, rows):
    pool = B.StringPool(b"\0")
    records = b"".join(B._encode_record(row, pool) for row in rows)
    strings = b"\0" + pool.appended()
    path.write_bytes(struct.pack("<4s4I", b"WDBC", len(rows), 234, 936, len(strings)) + records + strings)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    ds = root / "era-data/vanilla/mage.yaml"
    write_yaml(ds, {"era": 0, "class": 8, "tabs": [], "helpers": [{
        "id": 932980, "name": "Internal helper", "template": 116,
        "effects": [{"effect": 6, "aura": 33, "basePoints": -30, "targetA": 6}],
        "client": {"textKey": "spell.932980", "rank": 2, "icon": 285, "skillLine": 6}}]})
    (root / "era-data/datasets.txt").write_text("vanilla/mage.yaml data.sql custom.sql\n")
    locales = root / "client-patch/locales"
    english = {"name": "Chilled", "description": "Slowed by $s1%.", "auraDescription": ""}
    ru = {"name": "Окоченение", "description": "Скорость снижена на $s1%.", "auraDescription": "",
          "sourceHash": L.source_hash(english)}
    for locale, rank, entry in (("enUS", "Rank %s", english), ("ruRU", "Уровень %s", ru)):
        write_yaml(locales / locale / "common.yaml", {"schemaVersion": 1, "locale": locale, "texts": {"rank": rank}})
        write_yaml(locales / locale / "vanilla/mage.yaml", {"schemaVersion": 1, "locale": locale,
                   "era": "vanilla", "class": "mage", "texts": {"spell.932980": entry}})
    source = root / "source"
    source.mkdir()
    row = G._row_values({"ID": 116, "Effect_1": 6, "SpellVisualID_1": 42})
    row[136] = "Frostbolt"
    row[144] = "Ледяная стрела"
    row[178] = "Исходное описание"
    row[195] = "Исходная аура"
    write_dbc(source / "Spell.dbc", [row])
    (source / "SkillLineAbility.dbc").write_bytes(struct.pack("<4s4I", b"WDBC", 1, 14, 56, 1)
        + struct.pack("<14I", 10, 6, 116, *([0] * 11)) + b"\0")
    return root, ds, locales, source


def test_binary_ru_slot_utf8_and_original_records_preserved(project):
    root, ds, locales, source = project
    base = source / "Spell.dbc"
    before = base.read_bytes()
    out = root / "ru.dbc"
    B.build([ds], base, out, "1234abcd", locale="ruRU", locale_root=locales)
    rows = G._read_dbc_templates_uncached(out)
    row = rows[932980]
    assert row[144] == "Окоченение"
    assert row[161] == "Уровень 2"
    assert row[178] == "Скорость снижена на $s1%."
    assert row[195] == ""
    assert rows[932999][144] == "EraTalents Gen 1234abcd"
    assert row[G.COLS.index("SpellVisualID_1")] == 42
    for start in L.STRING_GROUPS.values():
        assert all(not row[start + slot] for slot in range(16) if slot != 8)
    assert out.read_bytes()[20:956] == before[20:956]
    assert base.read_bytes() == before
    assert rows[116][144] == "Ледяная стрела"


def test_locale_builds_share_all_nontext_fields(project):
    root, ds, locales, source = project
    rows = []
    for locale in ("enUS", "ruRU"):
        out = root / f"{locale}.dbc"
        B.build([ds], source / "Spell.dbc", out, "abcd1234", locale=locale, locale_root=locales)
        row = G._read_dbc_templates_uncached(out)[932980]
        for start in L.STRING_GROUPS.values():
            row[start:start + 17] = [0] * 17
        rows.append(row)
    assert rows[0] == rows[1]


@pytest.mark.parametrize("mutation,match", [
    (lambda d: d["texts"].clear(), "keys"),
    (lambda d: d["texts"]["spell.932980"].pop("name"), "fields"),
    (lambda d: d["texts"]["spell.932980"].update(sourceHash="old"), "stale"),
    (lambda d: d["texts"]["spell.932980"].update(description="Нет числа"), "tokens"),
    (lambda d: d["texts"]["spell.932980"].update(name=None), "text"),
    (lambda d: d.update(locale="deDE"), "locale"),
])
def test_incomplete_or_stale_translation_fails_before_writing(project, mutation, match):
    root, ds, locales, source = project
    path = locales / "ruRU/vanilla/mage.yaml"
    doc = L.load(path)
    mutation(doc)
    write_yaml(path, doc)
    out = root / "out.dbc"
    with pytest.raises(ValueError, match=match):
        B.build([ds], source / "Spell.dbc", out, locale="ruRU", locale_root=locales)
    assert not out.exists()


def test_other_incomplete_locales_do_not_block_selected_locale(project):
    _, ds, locales, _ = project
    (locales / "ruRU/common.yaml").write_text("invalid")
    L.catalogs([ds], "enUS", locales)


def test_duplicate_yaml_and_rank_format_rejected(project):
    _, ds, locales, _ = project
    path = locales / "ruRU/common.yaml"
    path.write_text("schemaVersion: 1\nschemaVersion: 1\n")
    with pytest.raises(ValueError, match="duplicate"):
        L.catalogs([ds], "ruRU", locales)
    write_yaml(path, {"schemaVersion": 1, "locale": "ruRU", "texts": {"rank": "Уровень %d"}})
    with pytest.raises(ValueError, match="%s"):
        L.catalogs([ds], "ruRU", locales)


def test_export_is_explicitly_untranslated_and_never_overwrites(project):
    root, ds, locales, _ = project
    target = locales / "deDE"
    L.export_template([ds], "deDE", target, locales)
    doc = L.load(target / "vanilla/mage.yaml")
    assert doc["texts"]["spell.932980"]["name"] is None
    assert doc["texts"]["spell.932980"]["auraDescription"] == ""
    with pytest.raises(ValueError):
        L.catalogs([ds], "deDE", locales)
    with pytest.raises(ValueError, match="overwrite"):
        L.export_template([ds], "deDE", target, locales)


def test_sla_extends_source_and_rebuild_is_stable(project):
    root, ds, _, source = project
    out = root / "ability.dbc"
    base = source / "SkillLineAbility.dbc"
    assert S.build([ds], base, out) == 1
    before = out.read_bytes()
    assert before[20:76] == base.read_bytes()[20:76]
    S.build([ds], out, out)
    assert out.read_bytes() == before


def test_wrong_source_locale_is_rejected(project):
    _, _, _, source = project
    with pytest.raises(ValueError, match="no names"):
        P.validate_source_locale(source / "Spell.dbc", "deDE")


def test_packaging_verifies_files_and_preserves_previous_output_on_failure(project, monkeypatch):
    root, ds, locales, source = project
    archive_files = {}
    fail = False

    def run(args, **kwargs):
        if args[0] == "pack":
            archive_files[args[2]] = pathlib.Path(args[3]).read_bytes()
            pathlib.Path(args[1]).write_bytes(b"synthetic archive")
        elif args[0] == "read":
            pathlib.Path(args[3]).write_bytes(b"bad" if fail else archive_files[args[2]])
        else:
            raise AssertionError(args)
    monkeypatch.setattr(P.subprocess, "run", run)
    out = root / "output/patch-V.mpq"
    manifest = P.build(source, "ruRU", out, root=root, locale_root=locales,
                       mpqpack="pack", mpqread="read", include_addon=False)
    assert set(archive_files) == {"DBFilesClient\\Spell.dbc", "DBFilesClient\\SkillLineAbility.dbc"}
    assert manifest["locale"] == "ruRU"
    assert json.loads(out.with_suffix(".mpq.json").read_text())["sha256"] == P.sha(out)
    previous = out.read_bytes()
    fail = True
    with pytest.raises(ValueError, match="verification"):
        P.build(source, "ruRU", out, root=root, locale_root=locales, force=True,
                mpqpack="pack", mpqread="read", include_addon=False)
    assert out.read_bytes() == previous


def test_committed_english_catalogs_cover_every_visible_spell():
    common, texts = L.catalogs(P.datasets(), "enUS")
    assert len(texts) == sum(bool(h.get("client")) for ds in P.datasets()
                             for h in G._load(ds).get("helpers", []) or [])


@pytest.mark.parametrize("dataset,sid,donor,expected", [
    ("mage", 932310, {"ID": 11366, "ManaCost": 0, "ManaCostPct": 22},
     {"ManaCost": 125, "ManaCostPct": 0}),
    ("shaman", 931353, {"ID": 3599, "SchoolMask": 1, "ManaCostPct": 5},
     {"ManaCost": 115, "ManaCostPct": 0, "SchoolMask": 4}),
])
def test_era_helpers_keep_costs_and_school_with_stock_donors(monkeypatch, dataset, sid, donor, expected):
    path = P.ROOT / "era-data/vanilla" / f"{dataset}.yaml"
    data = G._load(path)
    helper = next(h for h in data["helpers"] if h["id"] == sid)
    _, texts = L.catalogs([path], "enUS")
    monkeypatch.setattr(B.G, "_load", lambda p: {"helpers": [helper]})
    row = B._client_rows([path], {donor["ID"]: G._row_values(donor)}, texts=texts)[sid]
    for column, value in expected.items():
        assert row[G.COLS.index(column)] == value


def test_dbc_plural_prose_can_translate_but_formula_cannot_change():
    assert L._tokens("$34071s1 combo $lpoint:points;.") == L._tokens("$34071s1 $lприем:приема;.")
    assert L._tokens("${$m1*$m3/100}") != L._tokens("${$m1*$m3/10}")


@pytest.mark.parametrize("requested,selected", [("ruRU", "ruRU"), ("deDE", "enUS")])
def test_bundled_addon_loads_only_one_language(requested, selected):
    from lupa.lua51 import LuaRuntime
    with zipfile.ZipFile(io.BytesIO(P.addon_archive(P.ROOT, requested))) as archive:
        names = archive.namelist()
        other = "enUS" if selected == "ruRU" else "ruRU"
        assert not any(f"/generated/{other}/" in name for name in names)
        assert f"EraTalents/data/generated/{selected}/Common.lua" in names
        lua = LuaRuntime()
        lua.globals().GetLocale = lambda: requested
        for file in ("Locales.lua", f"{selected}/Common.lua", f"{selected}/MageVanilla.lua"):
            lua.execute(archive.read("EraTalents/data/generated/" + file).decode("utf-8"))
        assert lua.globals().EraTalents.locale == selected
        assert lua.globals().EraTalentsData[0][8].talents[1].name == (
            "Искусные чары" if selected == "ruRU" else "Arcane Subtlety")
