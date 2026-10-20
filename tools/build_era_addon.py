#!/usr/bin/env python3
"""Build every addon dataset and locale, validating all inputs before writing Lua.

Every locale, including enUS, lives in locales/{locale}/common.yaml plus
one {era}/{class}.yaml per datasets.txt entry, with schemaVersion, locale,
era, class, texts. Text keys are tree.<tab>, talent.<slug>, spell.<English name>;
values contain name, and talents also contain a complete tooltip list.
--export-locale ruRU --out DIR exports the complete English template to DIR.
Addon English text comes only from enUS catalogs. era-data remains the input
for mechanics and the existing server generators; its prose is not an addon fallback.
Normal builds also write client-addon/out/EraTalents-<version>.zip with the TOC and every
runtime file it loads. Locale initialization is compiled into EraTalents.lua
before the bootstrap, so it does not depend on a separate client file lookup.
Translated spell names must match the client's Spell.dbc. Native hyperlink
tooltips still come from the client patch, exactly as before.
"""
from __future__ import annotations

import argparse
import copy
import io
import pathlib
import re
import zipfile

import yaml
import gen_era_talents as G

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADDON = pathlib.Path("client-addon/EraTalents")
LOCALES = {"enUS", "enGB", "deDE", "esES", "esMX", "frFR", "itIT",
           "koKR", "ptBR", "ruRU", "zhCN", "zhTW"}
# Exact string.format signatures; prose percentages in talent tooltips are literal.
FORMATS = {"TALENTS": 0, "PET_TALENTS": 0, "RANK": 2, "NEXT_RANK": 0,
           "SPENT_TALENTS": 2, "UNSPENT_TALENTS": 1, "GLYPHS_UNAVAILABLE": 0,
           "SUMMON_PET": 0, "GENERATION_MISMATCH": 2, "MISSING": 0,
           "INSTANT": 0, "CAST_TIME": 1, "DECIMAL_SEPARATOR": 0, "LOCALE_FALLBACK": 2}


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load(path):
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def keys(value, expected, where):
    if not isinstance(value, dict):
        raise ValueError(f"{where}: expected a mapping")
    missing, extra = set(expected) - value.keys(), value.keys() - set(expected)
    if missing or extra:
        raise ValueError(f"{where}: missing {sorted(missing)}, unexpected {sorted(extra, key=str)}")


def text(value, where):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 and c != '\n' for c in value):
        raise ValueError(f"{where}: expected nonempty text without control characters")


def common(path, locale):
    doc = load(path)
    keys(doc, {"schemaVersion", "locale", "texts"}, path)
    if doc["schemaVersion"] != 1 or doc["locale"] != locale:
        raise ValueError(f"{path}: invalid schemaVersion or locale")
    values = doc["texts"]
    keys(values, FORMATS, path)
    for key, count in FORMATS.items():
        value = values[key]
        text(value, f"{path}: {key}")
        # Reject unsupported or malformed format tokens before the client.
        if re.findall(r"%(.)", value) != ["s"] * count or value.count('%') != count:
            raise ValueError(f"{path}: {key}: expected {count} %s placeholders")
    if len(values["DECIMAL_SEPARATOR"]) != 1:
        raise ValueError(f"{path}: DECIMAL_SEPARATOR must be one character")
    if values["CAST_TIME"].count("\n") or values["INSTANT"].count("\n"):
        raise ValueError(f"{path}: cast lines must be single-line text")
    return values


def dataset_schema(d):
    """Required text keys and rank counts, independent of server-authored prose."""
    values = {}
    def add(key, value):
        if key in values:
            raise ValueError(f"duplicate localization key: {key}")
        values[key] = value
    for tab in d["tabs"]:
        add(f"tree.{tab['key']}", None)
        for n in tab.get("nodes", []):
            add(f"talent.{n['slug']}", int(n["maxRank"]))
    for name in sorted(set(G.build_spell_mods(d)) | set(d.get("clientCastTimeBase", {}))):
        add(f"spell.{name}", None)
    return values


def validate_texts(values, d, where):
    expected = dataset_schema(d)
    keys(values, expected, where)
    for key, ranks in expected.items():
        entry = values[key]
        fields = {"name", "tooltip"} if ranks is not None else {"name"}
        keys(entry, fields, f"{where}: {key}")
        text(entry["name"], f"{where}: {key}.name")
        if ranks is not None:
            tips = entry["tooltip"]
            if not isinstance(tips, list) or len(tips) != ranks:
                raise ValueError(f"{where}: {key}.tooltip: need {ranks} ranks")
            for rank, tip in enumerate(tips, 1):
                text(tip, f"{where}: {key}.tooltip[{rank}]")
    names = [entry["name"] for key, entry in values.items() if key.startswith("spell.")]
    if len(set(names)) != len(names):
        raise ValueError(f"{where}: translated spell names collide")


def dataset_locale(path, locale, rel, d):
    doc = load(path)
    keys(doc, {"schemaVersion", "locale", "era", "class", "texts"}, path)
    if (doc["schemaVersion"], doc["locale"], doc["era"], doc["class"]) != (1, locale, rel.parent.name, rel.stem):
        raise ValueError(f"{path}: invalid locale metadata")
    validate_texts(doc["texts"], d, path)
    return doc["texts"]


def english_lua(d, values):
    """Compile the default tree using the same catalog contract as other locales."""
    tree = copy.deepcopy(d)
    for tab in tree["tabs"]:
        tab["name"] = values[f"tree.{tab['key']}"]["name"]
        for node in tab.get("nodes", []):
            node.update(copy.deepcopy(values[f"talent.{node['slug']}"]))
            specs = [node] if node.get("mechanic") == "spellmod" else [
                effect for effect in node.get("effects", []) if effect.get("type") == "spellmod"]
            for spec in specs:
                if spec.get("op") in G.DISCRETE_OPS:
                    spec["affects"] = [values[f"spell.{name}"]["name"] for name in spec.get("affects", [])]
    if tree.get("clientCastTimeBase"):
        tree["clientCastTimeBase"] = {values[f"spell.{name}"]["name"]: ms
                                      for name, ms in tree["clientCastTimeBase"].items()}
    source = G.emit_lua(tree)
    # The legacy emitter predates multiline catalogs. Escape newlines inside its
    # quoted Lua strings without changing the server generator or generation stamp.
    return re.sub(r'"(?:\\.|[^"\\])*"',
                  lambda match: match[0].replace("\n", "\\n").replace("\r", "\\r"), source)


def localized_lua(d, values, english):
    # Change only text on the already-loaded tree. All mechanics and texture
    # tokens remain exactly as emitted by the existing, generation-stamped tool.
    lines = [f"do local tree = EraTalentsData[{int(d['era'])}][{int(d['class'])}]\n"]
    for tab in d["tabs"]:
        name = values[f"tree.{tab['key']}"]["name"]
        lines.append(f"tree.tabs[{int(tab['key'])}].name = {lua_string(name)}\n")
    for index, (_, node) in enumerate(G._nodes(d), 1):
        entry = values[f"talent.{node['slug']}"]
        lines.append(f"tree.talents[{index}].name = {lua_string(entry['name'])}\n")
        tips = ", ".join(lua_string(tip) for tip in entry["tooltip"])
        lines.append(f"tree.talents[{index}].tooltip = {{ {tips} }}\n")
    for field, names in (("spellMods", G.build_spell_mods(d)),
                         ("castTimeBase", d.get("clientCastTimeBase", {}))):
        if names:
            entries = ", ".join(f"[{lua_string(values[f'spell.{name}']['name'])}] = "
                                f"tree.{field}[{lua_string(english[f'spell.{name}']['name'])}]"
                                for name in sorted(names))
            lines.append(f"tree.{field} = {{ {entries} }}\n")
    lines.append("end\n")
    return "".join(lines)


def lua_string(value):
    return G._lua_str(value).replace("\n", "\\n").replace("\r", "\\r")


def common_lua(values):
    return "EraTalents.L = {\n" + "".join(
        f"  {key} = {lua_string(value)},\n" for key, value in values.items()) + "}\n"


def release_archive(addon, entries, outputs):
    """Package exactly the TOC load set; fail before writing if a file is absent."""
    files = {"EraTalents.toc": (addon / "EraTalents.toc").read_bytes()}
    for entry in entries:
        rel = pathlib.PurePosixPath(entry)
        if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".lua":
            raise ValueError(f"EraTalents.toc: invalid runtime path: {entry}")
        path = addon / rel
        if path in outputs:
            files[entry] = outputs[path].encode("utf-8")
        else:
            try:
                files[entry] = path.read_bytes()
            except OSError as exc:
                raise ValueError(f"EraTalents.toc: missing runtime file {path}") from exc
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            info = zipfile.ZipInfo(f"EraTalents/{name}")
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return buffer.getvalue()


def release_path(root):
    toc = (root / ADDON / "EraTalents.toc").read_text(encoding="utf-8")
    match = re.search(r"^## Version: ([A-Za-z0-9_.-]+)$", toc, re.MULTILINE)
    if not match:
        raise ValueError("EraTalents.toc: missing or invalid release version")
    return root / "client-addon/out" / f"EraTalents-{match[1]}.zip"


def build(root=ROOT, *, check=False, export_locale=None, out=None):
    addon = root / ADDON
    datasets = []
    seen = set()
    for line in (root / "era-data/datasets.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3 or parts[0] in seen:
            raise ValueError(f"invalid/duplicate dataset manifest line: {line}")
        rel = pathlib.PurePosixPath(parts[0])
        if len(rel.parts) != 2 or '..' in rel.parts or rel.suffix != '.yaml':
            raise ValueError(f"invalid dataset path: {rel}")
        seen.add(parts[0])
        d = G._load(str(root / "era-data" / rel))
        G.lint(d)
        datasets.append((rel, d))
    english = common(addon / "locales/enUS/common.yaml", "enUS")
    # Catch missing English UI keys at build time as UI code evolves.
    for path in addon.glob("*.lua"):
        if path.name.startswith("test_"):
            continue
        for key in re.findall(r"\bET\.L\.([A-Z_]+)", path.read_text(encoding="utf-8")):
            if key not in english:
                raise ValueError(f"{path}: unknown localization key {key}")
    outputs = {}
    catalogs = {"enUS": {str(rel): dataset_locale(addon / "locales/enUS" / rel, "enUS", rel, d)
                          for rel, d in datasets}}
    lua = ["-- generated by tools/build_era_addon.py — DO NOT EDIT\n",
           "EraTalents = EraTalents or {}\n", common_lua(english),
           'EraTalents.locale = "enUS"\n',
           'local locale = GetLocale and GetLocale() or "enUS"\n',
           'EraTalents.clientLocale = locale\n']
    for locale_dir in sorted((addon / "locales").iterdir()):
        if not locale_dir.is_dir():
            continue
        locale = locale_dir.name
        if locale not in LOCALES:
            raise ValueError(f"{locale_dir}: unsupported client locale")
        expected_files = {"common.yaml", *(str(rel) for rel, _ in datasets)}
        actual_files = {p.relative_to(locale_dir).as_posix() for p in locale_dir.rglob("*") if p.is_file()}
        keys(dict.fromkeys(actual_files), expected_files, locale_dir)
        translated = english if locale == "enUS" else common(locale_dir / "common.yaml", locale)
        catalogs.setdefault(locale, {})
        if locale != "enUS":
            lua.extend([f"if locale == {lua_string(locale)} then\n",
                        f"EraTalents.locale = {lua_string(locale)}\n", common_lua(translated)])
        for rel, d in datasets:
            path = locale_dir / rel
            values = catalogs["enUS"][str(rel)] if locale == "enUS" else dataset_locale(path, locale, rel, d)
            catalogs[locale][str(rel)] = values
            if locale != "enUS":
                lua.append(localized_lua(d, values, catalogs["enUS"][str(rel)]))
        if locale != "enUS":
            lua.append("end\n")
    localization = "".join(lua)
    # Keep the pure localization intermediate for headless unit tests. The
    # deployed loader is embedded in the existing bootstrap entry instead.
    intermediate = addon / "data/generated/Localization.lua"
    outputs[intermediate] = localization
    outputs[addon / "EraTalents.lua"] = (localization + "\n" +
                                         (addon / "Bootstrap.lua").read_text(encoding="utf-8"))
    for rel, d in datasets:
        era = "TBC" if rel.parent.name == "tbc" else rel.parent.name.capitalize()
        outputs[addon / f"data/generated/{rel.stem.capitalize()}{era}.lua"] = english_lua(
            d, catalogs["enUS"][str(rel)])
    toc = (addon / "EraTalents.toc").read_text(encoding="utf-8").splitlines()
    entries = [line.replace('\\', '/') for line in toc if line and not line.startswith('#')]
    generated = {p.relative_to(addon).as_posix() for p in outputs
                 if p.parent.name == "generated" and p != intermediate}
    if {line for line in entries if line.startswith('data/generated/')} != generated:
        raise ValueError("EraTalents.toc: generated file list differs from datasets/localization output")
    if len(entries) != len(set(entries)):
        raise ValueError("EraTalents.toc: duplicate load entries")
    bootstrap_index = entries.index("EraTalents.lua")
    if any(entries.index(p) > bootstrap_index for p in generated):
        raise ValueError("EraTalents.toc: load trees before the bootstrap")
    if any(entries.index(p) < bootstrap_index for p in entries if p not in generated and p != "EraTalents.lua"):
        raise ValueError("EraTalents.toc: load the bootstrap before runtime modules")
    archive = release_archive(addon, entries, outputs)
    if export_locale:
        if export_locale not in LOCALES or export_locale == "enUS" or out is None:
            raise ValueError("--export-locale needs a non-English client locale and --out DIR")
        target = pathlib.Path(out)
        if target.exists():
            raise ValueError(f"refusing to overwrite locale template directory: {target}")
        docs = {"common.yaml": {"schemaVersion": 1, "locale": export_locale, "texts": english}}
        for rel, d in datasets:
            docs[str(rel)] = {"schemaVersion": 1, "locale": export_locale, "era": rel.parent.name,
                              "class": rel.stem, "texts": catalogs["enUS"][str(rel)]}
        for rel, doc in docs.items():
            path = target / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    elif not check:
        # Nothing is written until every locale, rank and TOC entry has passed.
        for path, content in outputs.items():
            if path.exists() and path.read_text(encoding="utf-8") == content:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        release = release_path(root)
        release.parent.mkdir(parents=True, exist_ok=True)
        release.write_bytes(archive)
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--export-locale")
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    try:
        build(check=args.check, export_locale=args.export_locale, out=args.out)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"addon build: {exc}\n")
    if not args.check and not args.export_locale:
        print(f"Deployment archive: {release_path(ROOT)}")


if __name__ == "__main__":
    main()
