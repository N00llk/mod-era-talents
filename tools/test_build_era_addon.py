"""Localization build failures and Lua 5.1 behavior; no WoW client required."""
import shutil
import hashlib
import json
import io
import zipfile

import pytest
import yaml

import build_era_addon as B


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    addon = root / B.ADDON
    shutil.copytree(B.ROOT / B.ADDON, addon, ignore=shutil.ignore_patterns("data", "locales"))
    english = addon / "locales/enUS"
    (english / "vanilla").mkdir(parents=True)
    for rel in ("common.yaml", "vanilla/warlock.yaml"):
        shutil.copy(B.ROOT / B.ADDON / "locales/enUS" / rel, english / rel)
    data = root / "era-data"
    (data / "vanilla").mkdir(parents=True)
    (data / "_ref").mkdir()
    shutil.copy(B.ROOT / "era-data/vanilla/warlock.yaml", data / "vanilla/warlock.yaml")
    shutil.copy(B.ROOT / "era-data/_ref/warlock-spells.yaml", data / "_ref/warlock-spells.yaml")
    (data / "datasets.txt").write_text("vanilla/warlock.yaml data.sql custom.sql\n")
    toc = addon / "EraTalents.toc"
    toc.write_text('\n'.join(line for line in toc.read_text().splitlines()
                             if not line.startswith('data\\generated\\') or
                             line in ('data\\generated\\WarlockVanilla.lua',
                                      'data\\generated\\Localization.lua')) + '\n')
    B.build(root)
    B.build(root, export_locale="ruRU", out=addon / "locales/ruRU")
    return root


def edit(root, relative, fn, locale="ruRU"):
    path = root / B.ADDON / "locales" / locale / relative
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(doc)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")


@pytest.fixture(scope="module")
def compiled_outputs():
    return B.build(check=True)


def test_all_english_trees_match_generated_data(compiled_outputs):
    outputs = compiled_outputs
    for path, content in outputs.items():
        if path.name == "Localization.lua":
            continue
        assert content == path.read_text(encoding="utf-8")


@pytest.mark.parametrize("locale", ["enUS", "ruRU"])
@pytest.mark.parametrize("relative", ["common.yaml", "vanilla/warlock.yaml"])
def test_missing_file_fails_before_writing(project, relative, locale):
    addon = project / B.ADDON
    (addon / "locales" / locale / relative).unlink()
    generated = addon / "data/generated/Localization.lua"
    previous = generated.read_bytes()
    with pytest.raises(ValueError, match="missing|No such file"):
        B.build(project)
    assert generated.read_bytes() == previous


@pytest.mark.parametrize("locale", ["enUS", "ruRU"])
@pytest.mark.parametrize("mutation, message", [
    (lambda d: d["texts"].pop("RANK"), "missing"),
    (lambda d: d["texts"].update(RANK="Ранг %s"), "placeholders"),
    (lambda d: d["texts"].update(RANK="Ранг %d/%s"), "placeholders"),
    (lambda d: d["texts"].update(RANK="Ранг %s/%s%"), "placeholders"),
    (lambda d: d["texts"].update(NEXT_RANK="  "), "nonempty"),
    (lambda d: d["texts"].update(NEXT_RANK=42), "nonempty"),
    (lambda d: d["texts"].update(TYPO="extra"), "unexpected"),
    (lambda d: d.update(locale="deDE"), "locale"),
    (lambda d: d.update(schemaVersion=2), "schemaVersion"),
])
def test_invalid_common_rejected(project, mutation, message, locale):
    edit(project, "common.yaml", mutation, locale=locale)
    with pytest.raises(ValueError, match=message):
        B.build(project)


@pytest.mark.parametrize("locale", ["enUS", "ruRU"])
@pytest.mark.parametrize("mutation, message", [
    (lambda d: d["texts"].pop("tree.1"), "missing"),
    (lambda d: d["texts"].pop("spell.Corruption"), "missing"),
    (lambda d: next(v for k, v in d["texts"].items() if k.startswith("talent."))["tooltip"].pop(), "ranks"),
    (lambda d: next(v for k, v in d["texts"].items() if k.startswith("talent."))["tooltip"].append("extra"), "ranks"),
    (lambda d: next(v for k, v in d["texts"].items() if k.startswith("talent."))["tooltip"].__setitem__(0, ""), "nonempty"),
    (lambda d: d.update(era="tbc"), "metadata"),
    (lambda d: d["texts"].update({"spell.Does not exist": {"name": "stale"}}), "unexpected"),
])
def test_invalid_talent_data_rejected(project, mutation, message, locale):
    edit(project, "vanilla/warlock.yaml", mutation, locale=locale)
    with pytest.raises(ValueError, match=message):
        B.build(project)


def test_duplicate_keys_rejected(project):
    path = project / B.ADDON / "locales/ruRU/common.yaml"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("locale: ruRU\n")
    with pytest.raises(ValueError, match="duplicate YAML key"):
        B.build(project)


def test_spell_name_collisions_rejected(project):
    def collide(doc):
        for key, value in doc["texts"].items():
            if key.startswith("spell."):
                value["name"] = "Same spell"
    edit(project, "vanilla/warlock.yaml", collide)
    with pytest.raises(ValueError, match="collide"):
        B.build(project)


def test_every_locale_validated_even_when_english_is_selected(project):
    addon = project / B.ADDON
    shutil.copytree(addon / "locales/ruRU", addon / "locales/deDE")
    with pytest.raises(ValueError, match="locale"):
        B.build(project)


def test_unknown_ui_key_rejected(project):
    path = project / B.ADDON / "TalentUI.lua"
    with path.open("a", encoding="utf-8") as stream:
        stream.write('\nlocal label = ET.L.NEW_LABEL\n')
    with pytest.raises(ValueError, match="NEW_LABEL"):
        B.build(project)


def test_invalid_english_rank_rejected(project):
    edit(project, "vanilla/warlock.yaml",
         lambda doc: next(value for key, value in doc["texts"].items()
                          if key.startswith("talent."))["tooltip"].pop(), locale="enUS")
    with pytest.raises(ValueError, match="ranks"):
        B.build(project)


def lua_runtime():
    lupa = pytest.importorskip("lupa.lua51", reason="install lupa to exercise actual Lua 5.1")
    return lupa.LuaRuntime(unpack_returned_tuples=True)


@pytest.mark.parametrize("locale", ["enUS", "enGB", "frFR", None])
def test_compiled_english_matches_pre_migration_lua(compiled_outputs, locale):
    """Frozen hashes were captured from all 18 original generated trees in Lua 5.1.

    They cover every table field, including all 1,011 talents, all rank tooltips,
    spell modifiers, prerequisites, backgrounds and granted spell IDs.
    """
    lua = lua_runtime()
    lua.execute((B.ROOT / "tools/fixtures/era_addon_boot.lua").read_text(encoding="utf-8"))
    if locale is not None:
        lua.globals().GetLocale = lambda: locale
    addon = B.ROOT / B.ADDON
    for line in (addon / "EraTalents.toc").read_text().splitlines():
        path = addon / line.replace('\\', '/')
        if path in compiled_outputs:
            lua.execute(compiled_outputs[path])
    snapshots = json.loads((B.ROOT / "tools/fixtures/era_addon_enUS_data.json").read_text())
    def canonical(table):
        return {str(key): canonical(value) if hasattr(value, "items") else value
                for key, value in table.items()}
    for rel, expected in snapshots.items():
        doc = B.load(addon / "locales/enUS" / rel)
        era = {"vanilla": 0, "tbc": 1}[doc["era"]]
        class_id = next(key for key, token in B.G.CLASS_TOKENS.items() if token.lower() == doc["class"])
        tree = lua.globals().EraTalentsData[era][class_id]
        digest = hashlib.sha256(json.dumps(canonical(tree), sort_keys=True, ensure_ascii=False).encode("utf-8"))
        assert digest.hexdigest() == expected, rel
    assert lua.globals().EraTalents.locale == "enUS"


def test_english_catalog_is_the_addon_text_source(project):
    def translate(doc):
        doc["texts"]["tree.1"]["name"] = "Catalog tree"
        first = next(value for key, value in doc["texts"].items() if key.startswith("talent."))
        first["name"] = 'Catalog "talent"'
        first["tooltip"][0] = 'Catalog line one\nLine two: 10% and \\path'
        doc["texts"]["spell.Corruption"]["name"] = "Catalog Corruption"
    edit(project, "vanilla/warlock.yaml", translate, locale="enUS")
    source_path = project / "era-data/vanilla/warlock.yaml"
    source = B.load(source_path)
    source["tabs"][0]["name"] = "Server text must not appear"
    source["tabs"][0]["nodes"][0]["name"] = "Server talent must not appear"
    source["tabs"][0]["nodes"][0]["tooltip"][0] = "Server tooltip must not appear"
    source_path.write_text(yaml.safe_dump(source), encoding="utf-8")
    outputs = B.build(project)
    for locale in ("enUS", "ruRU"):
        lua = lua_runtime()
        lua.globals().GetLocale = lambda: locale
        for path, content in sorted(outputs.items(), key=lambda pair: pair[0].name == "Localization.lua"):
            if path.parent.name != "generated":
                continue
            lua.execute(content)
        tree = lua.globals().EraTalentsData[0][9]
        if locale == "enUS":
            assert tree.tabs[1].name == "Catalog tree"
            assert tree.talents[1].name == 'Catalog "talent"'
            assert tree.talents[1].tooltip[1] == 'Catalog line one\nLine two: 10% and \\path'
            assert tree.castTimeBase["Catalog Corruption"] == 2000
            assert tree.spellMods["Catalog Corruption"][1].attr == "castTime"
        else:
            assert tree.castTimeBase["Corruption"] == 2000
            assert tree.spellMods["Corruption"][1].attr == "castTime"
        assert tree.talents[1].name != "Server talent must not appear"
    # New translation templates must come from the authoritative enUS catalog.
    target = project / "translation-template"
    B.build(project, export_locale="deDE", out=target)
    assert B.load(target / "vanilla/warlock.yaml")["texts"]["tree.1"]["name"] == "Catalog tree"


def test_locale_selection_and_translated_lookup(project):
    def ui(doc):
        doc["texts"].update(TALENTS="Таланты", INSTANT="Мгновенно",
                            CAST_TIME="Применение: %s сек.", DECIMAL_SEPARATOR=",")
    edit(project, "common.yaml", ui)
    def talents(doc):
        doc["texts"]["tree.1"]["name"] = "Колдовство"
        doc["texts"]["spell.Corruption"]["name"] = "Порча"
        for key, value in doc["texts"].items():
            if key.startswith("talent."):
                value["name"] = 'Талант "имя"'
                value["tooltip"] = [f"Строка {rank}\nЭффект 10%." for rank, _ in enumerate(value["tooltip"], 1)]
    edit(project, "vanilla/warlock.yaml", talents)
    outputs = B.build(project)
    for locale in ("enUS", "ruRU", "frFR", "enGB"):
        lua = lua_runtime()
        lua.globals().GetLocale = lambda: locale
        for path, source in sorted(outputs.items(), key=lambda pair: pair[0].name == "Localization.lua"):
            if path.parent.name != "generated":
                continue
            lua.execute(source)
        et = lua.globals().EraTalents
        tree = lua.globals().EraTalentsData[0][9]
        assert et.locale == ("ruRU" if locale == "ruRU" else "enUS")
        assert et.L.TALENTS == ("Таланты" if locale == "ruRU" else "Talents")
        if locale == "ruRU":
            assert tree.tabs[1].name == "Колдовство"
            assert tree.talents[1].name == 'Талант "имя"'
            assert '\n' in tree.talents[1].tooltip[1]
            assert tree.castTimeBase["Порча"] == 2000
            assert tree.castTimeBase["Corruption"] is None
            assert tree.spellMods["Порча"][1].attr == "castTime"
            assert tree.spellMods["Corruption"] is None
            lua.execute((B.ROOT / B.ADDON / "Tooltip.lua").read_text(encoding="utf-8"))
            assert et.RewriteCastBase("Мгновенно", 2000, -400, 1) == "Применение: 1,6 сек."
            assert et.RewriteCastBase("Применение: 1,6 сек.", 2000, -400, 1) == "Применение: 1,6 сек."
            assert et.RewriteCastBase("Применение: 2 сек.", 2000, -2000, 1) == "Мгновенно"
            assert et.RewriteCastBase("Other line", 2000, 0, 1) is None


@pytest.mark.parametrize("name", ["test_comms.lua", "test_hook.lua", "test_inspect.lua", "test_tooltip.lua"])
def test_existing_lua_regressions(name):
    lua = lua_runtime()
    lua.execute(f'dofile("client-addon/EraTalents/{name}")')


@pytest.mark.parametrize("locale", ["ruRU", "enUS", "enGB"])
def test_release_archive_login_and_locale_fallback(compiled_outputs, locale):
    addon = B.ROOT / B.ADDON
    entries = [line.replace('\\', '/') for line in (addon / "EraTalents.toc").read_text().splitlines()
               if line and not line.startswith('#')]
    data = B.release_archive(addon, entries, compiled_outputs)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        expected = {"EraTalents/EraTalents.toc", *(f"EraTalents/{entry}" for entry in entries)}
        assert set(archive.namelist()) == expected
        assert "EraTalents/data/generated/Localization.lua" not in expected
        assert archive.testzip() is None
        lua = lua_runtime()
        lua.execute((B.ROOT / "tools/fixtures/era_addon_boot.lua").read_text(encoding="utf-8"))
        lua.globals().GetLocale = lambda: locale
        # Read the packaged TOC, rather than a source-file list that might be stale.
        for line in archive.read("EraTalents/EraTalents.toc").decode("utf-8").splitlines():
            if line and not line.startswith('#'):
                lua.execute(archive.read("EraTalents/" + line.replace('\\', '/')).decode("utf-8"))
        lua.globals().TestEnterWorld()
        et = lua.globals().EraTalents
        assert et.locale == "enUS"
        assert et.clientLocale == locale
        assert et._classId == 2
        assert et.frame.title.text == "Talents"
        assert et.frame.shown is False
        assert et.frame.petTalents.text == "Pet Talents"
        assert et.frame.petTalents.shown is False
        assert lua.globals().testSent[1] == "HELLO"
        if locale == "enUS":
            assert len(lua.globals().testChat) == 0
        else:
            assert len(lua.globals().testChat) == 1
            assert f"translations for {locale} are not available; using enUS" in lua.globals().testChat[1]
        lua.globals().TestEnterWorld()
        assert len(lua.globals().testChat) == (0 if locale == "enUS" else 1)


def test_missing_runtime_file_fails_before_writing(project):
    addon = project / B.ADDON
    archive = B.release_path(project)
    previous = archive.read_bytes()
    (addon / "TalentUI.lua").unlink()
    with pytest.raises(ValueError, match="missing runtime file"):
        B.build(project)
    assert archive.read_bytes() == previous


def test_stale_toc_cannot_require_separate_localization(project):
    toc = project / B.ADDON / "EraTalents.toc"
    toc.write_text(toc.read_text() + 'data\\generated\\Localization.lua\n')
    with pytest.raises(ValueError, match="generated file list differs"):
        B.build(project)


def test_supported_locale_login_does_not_warn(project):
    edit(project, "common.yaml", lambda doc: doc["texts"].update(TALENTS="Таланты"))
    B.build(project)
    lua = lua_runtime()
    lua.execute((B.ROOT / "tools/fixtures/era_addon_boot.lua").read_text(encoding="utf-8"))
    lua.globals().GetLocale = lambda: "ruRU"
    with zipfile.ZipFile(B.release_path(project)) as archive:
        for line in archive.read("EraTalents/EraTalents.toc").decode("utf-8").splitlines():
            if line and not line.startswith('#'):
                lua.execute(archive.read("EraTalents/" + line.replace('\\', '/')).decode("utf-8"))
    lua.globals().TestEnterWorld()
    assert lua.globals().EraTalents.locale == "ruRU"
    assert lua.globals().EraTalents.frame.title.text == "Таланты"
    assert len(lua.globals().testChat) == 0


def test_login_survives_client_refusing_separate_localization_file(compiled_outputs):
    """Reproduce FrameXML.log's failed file lookup before loading the bootstrap."""
    lua = lua_runtime()
    lua.execute((B.ROOT / "tools/fixtures/era_addon_boot.lua").read_text(encoding="utf-8"))
    lua.globals().GetLocale = lambda: "ruRU"
    addon = B.ROOT / B.ADDON
    entries = [line.replace('\\', '/') for line in (addon / "EraTalents.toc").read_text().splitlines()
               if line and not line.startswith('#')]
    failed = []
    for entry in entries:
        if entry == "EraTalents.lua":
            # The client's separate-file load fails; execute none of that file.
            failed.append("data/generated/Localization.lua")
            assert lua.globals().EraTalents is None
        path = addon / entry
        source = compiled_outputs[path] if path in compiled_outputs else path.read_text(encoding="utf-8")
        lua.execute(source)
    lua.globals().TestEnterWorld()
    assert failed == ["data/generated/Localization.lua"]
    assert lua.globals().EraTalents.L.TALENTS == "Talents"
    assert lua.globals().EraTalents.frame.title.text == "Talents"
    assert lua.globals().EraTalents.frame.shown is False
    assert "using enUS" in lua.globals().testChat[1]


def test_ui_failure_keeps_new_frame_hidden_and_boot_incomplete(compiled_outputs):
    lua = lua_runtime()
    lua.execute((B.ROOT / "tools/fixtures/era_addon_boot.lua").read_text(encoding="utf-8"))
    addon = B.ROOT / B.ADDON
    for line in (addon / "EraTalents.toc").read_text().splitlines():
        if line and not line.startswith('#'):
            path = addon / line.replace('\\', '/')
            source = compiled_outputs[path] if path in compiled_outputs else path.read_text(encoding="utf-8")
            lua.execute(source)
    # Inject the reported failure after the embedded loader has initialized it.
    lua.execute('EraTalents.L = nil; testBootOK = pcall(TestEnterWorld)')
    assert lua.globals().testBootOK is False
    assert lua.globals().EraTalentFrame.shown is False
    assert lua.globals().EraTalents._inited is None
