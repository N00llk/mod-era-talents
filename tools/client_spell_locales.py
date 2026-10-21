"""Single-locale spell catalogs and the binary 3.3.5a localized-string layout.

SQL spell_dbc locale column labels are NOT the binary client's locale order.
Keep this map separate from gen_era_talents.COLS.
"""
from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCALES = {"enUS": 0, "enGB": 0, "koKR": 1, "frFR": 2, "deDE": 3,
           "zhCN": 4, "zhTW": 5, "esES": 6, "esMX": 7, "ruRU": 8}
STRING_GROUPS = {"name": 136, "rank": 153, "description": 170, "auraDescription": 187}
TEXT_FIELDS = {"name", "description", "auraDescription"}
DEFAULT_ROOT = ROOT / "client-patch/locales"


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for key, value in node.value:
        key = loader.construct_object(key)
        if key in result:
            raise ValueError(f"duplicate YAML key: {key}")
        result[key] = loader.construct_object(value)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load(path):
    return yaml.load(pathlib.Path(path).read_text(encoding="utf-8"), Loader=UniqueLoader)


def source_hash(entry):
    return hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _text(value, where, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()) or any(
            ord(c) < 32 and c != "\n" for c in value):
        raise ValueError(f"{where}: expected {'possibly empty ' if empty else 'nonempty '}text")


def _tokens(value):
    # Preserve DBC numeric references and formatting commands, including gender/plural
    # branches. Their surrounding prose may be translated and reordered.
    commands = re.findall(r"\$(?:\d+)?(?:@[A-Za-z]+\d*|[A-Za-z]\d*|[?:;])|\|[A-Za-z]", value)
    # Arithmetic must keep its operators and constants too, not only $sN tokens.
    commands.extend(re.findall(r"\$\{[^}]*\}", value))
    return sorted(commands)


def _document(path, locale, rel=None):
    doc = load(path)
    expected = {"schemaVersion", "locale", "texts"} if rel is None else {
        "schemaVersion", "locale", "era", "class", "texts"}
    if not isinstance(doc, dict) or set(doc) != expected:
        raise ValueError(f"{path}: invalid catalog fields")
    if doc["schemaVersion"] != 1 or doc["locale"] != locale:
        raise ValueError(f"{path}: invalid schemaVersion or locale")
    if rel is not None and (doc["era"], doc["class"]) != (rel.parent.name, rel.stem):
        raise ValueError(f"{path}: invalid era/class")
    if not isinstance(doc["texts"], dict):
        raise ValueError(f"{path}: expected texts mapping")
    return doc["texts"]


def catalogs(dataset_paths, locale, root=DEFAULT_ROOT):
    """Validate only the requested language and its English source. No fallback."""
    if locale not in LOCALES:
        raise ValueError(f"unsupported 3.3.5a locale: {locale}")
    root = pathlib.Path(root)
    common = _document(root / locale / "common.yaml", locale)
    if set(common) != {"rank"}:
        raise ValueError("common.yaml: expected rank format")
    _text(common["rank"], "rank format")
    if "\n" in common["rank"]:
        raise ValueError("rank format must be a single line")
    if common["rank"].count("%s") != 1 or common["rank"].replace("%s", "").count("%"):
        raise ValueError("rank format: expected exactly one %s")
    result = {}
    for path in dataset_paths:
        path = pathlib.Path(path)
        rel = pathlib.Path(path.parent.name) / path.name
        dataset = load(path)
        helpers = [h for h in dataset.get("helpers", []) or [] if h.get("client")]
        expected = {h["client"]["textKey"] for h in helpers}
        if len(expected) != len(helpers):
            raise ValueError(f"{path}: duplicate client textKey")
        for h in helpers:
            if TEXT_FIELDS & h["client"].keys():
                raise ValueError(f"{path}: helper {h['id']}: text belongs in the locale catalog")
        english = _document(root / "enUS" / rel, "enUS", rel)
        selected = english if locale == "enUS" else _document(root / locale / rel, locale, rel)
        if set(english) != expected or set(selected) != expected:
            raise ValueError(f"{locale}/{rel}: missing or obsolete spell text keys")
        for key in sorted(expected):
            source = english[key]
            if not isinstance(source, dict) or "name" not in source or not set(source) <= TEXT_FIELDS:
                raise ValueError(f"{rel}: {key}: invalid English text fields")
            for field, value in source.items():
                _text(value, f"enUS/{rel}: {key}.{field}", empty=field != "name")
            entry = selected[key]
            fields = set(source) | ({"sourceHash"} if locale != "enUS" else set())
            if not isinstance(entry, dict) or set(entry) != fields:
                raise ValueError(f"{locale}/{rel}: {key}: missing or obsolete fields")
            if locale != "enUS" and entry["sourceHash"] != source_hash(source):
                raise ValueError(f"{locale}/{rel}: {key}: translation is stale (sourceHash)")
            for field in source:
                _text(entry[field], f"{locale}/{rel}: {key}.{field}", empty=source[field] == "")
                if field == "name" and "\n" in entry[field]:
                    raise ValueError(f"{locale}/{rel}: {key}.name must be a single line")
                if _tokens(entry[field]) != _tokens(source[field]):
                    raise ValueError(f"{locale}/{rel}: {key}.{field}: changed DBC tokens")
            if key in result:
                raise ValueError(f"duplicate spell text key across datasets: {key}")
            result[key] = {field: entry[field] for field in source}
    return common, result


def export_template(dataset_paths, locale, out, root=DEFAULT_ROOT):
    """Export untranslated entries as null; a template cannot ship as a translation."""
    if locale not in LOCALES or locale == "enUS":
        raise ValueError("select a supported non-English locale")
    catalogs(dataset_paths, "enUS", root)
    out = pathlib.Path(out)
    if out.exists():
        raise ValueError(f"refusing to overwrite {out}")
    docs = {pathlib.Path("common.yaml"): {"schemaVersion": 1, "locale": locale,
                                          "texts": {"rank": None}}}
    for path in dataset_paths:
        path = pathlib.Path(path)
        rel = pathlib.Path(path.parent.name) / path.name
        doc = copy.deepcopy(load(pathlib.Path(root) / "enUS" / rel))
        doc["locale"] = locale
        for key, entry in doc["texts"].items():
            doc["texts"][key] = {field: "" if value == "" else None for field, value in entry.items()}
            doc["texts"][key]["sourceHash"] = source_hash(entry)
        docs[rel] = doc
    for rel, doc in docs.items():
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
