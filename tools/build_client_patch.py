"""Build one locale's client patch from user-supplied 3.3.5a DBCs.

No IP archive or installed client is read or modified. Sources must be the final
official build-12340 Spell.dbc and SkillLineAbility.dbc for the selected locale.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import subprocess
import tempfile
import zipfile

import build_client_dbc as spells
import build_client_skilllineability as skills
import build_era_addon as addon
import client_spell_locales as L
import gen_era_talents as G

ROOT = pathlib.Path(__file__).resolve().parents[1]


def datasets(root=ROOT):
    result = []
    for line in (root / "era-data/datasets.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        rel = pathlib.PurePosixPath(parts[0])
        if len(parts) != 3 or len(rel.parts) != 2 or ".." in rel.parts or rel.suffix != ".yaml":
            raise ValueError(f"invalid dataset manifest entry: {line}")
        path = root / "era-data" / rel
        if path in result:
            raise ValueError(f"duplicate dataset: {rel}")
        result.append(path)
    if not result:
        raise ValueError("empty dataset manifest")
    return result


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def validate_source_locale(path, locale):
    # An MPQ/DBC filename does not identify its language. Require populated names
    # in the selected binary locale slot before producing any output.
    rows = G.read_dbc_templates(path)
    slot = L.STRING_GROUPS["name"] + L.LOCALES[locale]
    if not any(row[slot] for row in rows.values()):
        raise ValueError(f"{path}: no names in requested {locale} slot")


def addon_archive(root, locale):
    """Package one addon language for this MPQ; use the addon's English fallback
    when its UI has no translation for the requested spell locale.
    """
    outputs = addon.build(root, check=True)
    addon_dir = root / addon.ADDON
    generated = addon_dir / "data/generated"
    selected = locale if generated / locale / "Common.lua" in outputs else "enUS"
    outputs[generated / "Locales.lua"] = (
        "-- generated for this locale-specific client patch\n"
        "EraTalents = EraTalents or {}\n"
        'EraTalents.clientLocale = GetLocale and GetLocale() or "enUS"\n'
        f'EraTalents.locale = "{selected}"\n')
    toc_path = addon_dir / "EraTalents.toc"
    lines = outputs[toc_path].splitlines()
    entries = [line.replace("\\", "/") for line in lines if line and not line.startswith("#")]
    entries = [entry for entry in entries if not entry.startswith("data/generated/")
               or entry == "data/generated/Locales.lua"
               or entry.startswith(f"data/generated/{selected}/")]
    outputs[toc_path] = "\n".join([line for line in lines if line.startswith("#")]
                                + [entry.replace("/", "\\") for entry in entries]) + "\n"
    return addon.release_archive(addon_dir, entries, outputs)


def build(source, locale, out, *, root=ROOT, locale_root=None,
          mpqpack=None, mpqread=None, force=False, include_addon=True):
    source, out = pathlib.Path(source).resolve(), pathlib.Path(out).resolve()
    locale_root = pathlib.Path(locale_root or root / "client-patch/locales")
    paths = datasets(root)
    common, texts = L.catalogs(paths, locale, locale_root)
    inputs = {name: source / name for name in ("Spell.dbc", "SkillLineAbility.dbc")}
    for path in inputs.values():
        if not path.is_file():
            raise ValueError(f"missing original client DBC: {path}")
    if out in inputs.values():
        raise ValueError("output must not overwrite source DBCs")
    manifest_out = out.with_suffix(out.suffix + ".json")
    if not force and (out.exists() or manifest_out.exists()):
        raise ValueError(f"output already exists: {out} (use --force)")
    pack = mpqpack or os.environ.get("MPQPACK", str(root / "client-patch/mpqpack"))
    read = mpqread or os.environ.get("MPQREAD", str(root / "client-patch/mpqread"))
    validate_source_locale(inputs["Spell.dbc"], locale)
    input_hashes = {name: sha(path) for name, path in inputs.items()}
    stamp = G.generation_stamp(paths)
    addon_zip = addon_archive(root, locale) if include_addon else None
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="era-client-", dir=out.parent) as temp:
        stage = pathlib.Path(temp)
        spell = stage / "Spell.dbc"
        count = spells.build(paths, inputs["Spell.dbc"], spell, stamp,
                             locale=locale, locale_root=locale_root)
        ability = stage / "SkillLineAbility.dbc"
        skills.build(paths, inputs["SkillLineAbility.dbc"], ability)
        files = {"DBFilesClient\\Spell.dbc": spell,
                 "DBFilesClient\\SkillLineAbility.dbc": ability}
        if addon_zip is not None:
            with zipfile.ZipFile(io.BytesIO(addon_zip)) as archive:
                for index, entry in enumerate(archive.infolist()):
                    file = stage / f"addon-{index}"
                    file.write_bytes(archive.read(entry))
                    files["Interface\\AddOns\\" + entry.filename.replace("/", "\\")] = file
        archive_path = stage / "patch-V.mpq"
        for internal, file in files.items():
            subprocess.run([str(pack), str(archive_path), internal, str(file)], check=True,
                           stdout=subprocess.DEVNULL)
        # Check extracted contents, rather than trusting archive membership alone.
        verified = stage / "verified"
        for internal, file in files.items():
            subprocess.run([str(read), str(archive_path), internal, str(verified)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if verified.read_bytes() != file.read_bytes():
                raise ValueError(f"MPQ verification failed: {internal}")
        if input_hashes != {name: sha(path) for name, path in inputs.items()}:
            raise ValueError("source DBCs changed during build")
        manifest = {"schemaVersion": 1, "locale": locale, "clientBuild": 12340,
                    "generation": stamp, "inputs": input_hashes,
                    "translationHash": L.source_hash({"common": common, "texts": texts}),
                    "clientSpellRows": count, "addonBundled": include_addon,
                    "files": {name: sha(file) for name, file in files.items()},
                    "sha256": sha(archive_path)}
        staged_manifest = stage / "manifest.json"
        staged_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Publish only after all generation and archive checks pass.
        os.replace(archive_path, out)
        os.replace(staged_manifest, manifest_out)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locale", required=True, choices=L.LOCALES)
    ap.add_argument("--source-dbc", type=pathlib.Path)
    ap.add_argument("--locale-root", type=pathlib.Path, default=L.DEFAULT_ROOT)
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--export-locale", action="store_true", help="export an untranslated catalog template to --out")
    ap.add_argument("--check", action="store_true", help="validate selected spell catalogs without building")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--without-addon", action="store_true")
    ap.add_argument("--mpqpack")
    ap.add_argument("--mpqread")
    args = ap.parse_args()
    try:
        if args.export_locale:
            if args.out is None:
                raise ValueError("--export-locale requires --out DIR")
            L.export_template(datasets(), args.locale, args.out, args.locale_root)
        elif args.check:
            L.catalogs(datasets(), args.locale, args.locale_root)
            print(f"Spell catalogs valid: {args.locale}")
        else:
            if args.source_dbc is None:
                raise ValueError("--source-dbc DIR is required; IP patch inputs are no longer supported")
            out = args.out or ROOT / "client-patch/out" / args.locale / "patch-V.mpq"
            result = build(args.source_dbc, args.locale, out, locale_root=args.locale_root,
                           mpqpack=args.mpqpack, mpqread=args.mpqread, force=args.force,
                           include_addon=not args.without_addon)
            print(f"Built {args.locale}: {out} (SHA256 {result['sha256']})")
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        ap.exit(1, f"client patch: {exc}\n")


if __name__ == "__main__":
    main()
