#!/usr/bin/env python3
"""Migration globale jarvis → fedex-v0 (code: fedex_v0)."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".cursor",
    ".pytest_cache",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    "site-packages",
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".html", ".css", ".scss", ".json", ".md",
    ".toml", ".txt", ".sh", ".ps1", ".yaml", ".yml", ".env", ".example",
    ".ini", ".cfg", ".xml", ".svg", ".c", ".h", ".lock", ".bat", ".cmd",
    ".jsx", ".mjs", ".sql", ".jinja", ".j2", ".properties",
}

SPECIAL_RENAMES = {
    "jarvis": "fedex-v0",
    "jarvis.ps1": "fedex-v0.ps1",
    "JARVISINTERFACEGITHUB.png": "fedex-v0-interface.png",
    "CDC_jarvis_evolution.md": "CDC_fedex_v0_evolution.md",
    "jarvis_stats.py": "fedex_v0_stats.py",
    "jarvis.py": "fedex_v0.py",
}


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.endswith(".egg-info")


def replace_content(text: str) -> str:
    rules = [
        ("push_jarvis_alert", "push_fedex_v0_alert"),
        ("_handle_push_jarvis_alert", "_handle_push_fedex_v0_alert"),
        ("JARVISINTERFACEGITHUB", "FEDEX_V0_INTERFACE"),
        ("jarvis-os", "fedex-v0"),
        ("Jarvis-OS", "fedex-v0"),
        ("JARVIS_", "FEDEX_V0_"),
        ("JARVIS", "FEDEX_V0"),
        ("Jarvis OS", "fedex-v0"),
        ("Jarvis vocal", "fedex-v0 vocal"),
        ("Jarvis prêt", "fedex-v0 prêt"),
        ("Jarvis arrêté", "fedex-v0 arrêté"),
        ("Usage : jarvis", "Usage : fedex-v0"),
        ("Jarvis", "fedex-v0"),
        ("jarvis_", "fedex_v0_"),
        ("jarvis.", "fedex_v0."),
        ("jarvis/", "fedex_v0/"),
        ("jarvis\\", "fedex_v0\\"),
        ("jarvis", "fedex_v0"),
    ]
    out = text
    for old, new in rules:
        out = out.replace(old, new)
    return out


def iter_files() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
        for name in filenames:
            p = Path(dirpath) / name
            if p == Path(__file__).resolve():
                continue
            if p.suffix.lower() in TEXT_EXTENSIONS or name in {".env", ".env.example", "fedex-v0", "jarvis"}:
                files.append(p)
            elif name in SPECIAL_RENAMES or "jarvis" in name.lower():
                files.append(p)
    return files


def migrate_content() -> int:
    changed = 0
    for path in iter_files():
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not re.search(r"jarvis|Jarvis|JARVIS", text):
            continue
        new_text = replace_content(text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8", newline="\n")
            changed += 1
    return changed


def rename_paths() -> int:
    renames: list[tuple[Path, Path]] = []

    for dirpath, dirnames, filenames in os.walk(ROOT, topdown=False):
        if any(should_skip_dir(p) for p in Path(dirpath).parts):
            continue
        base = Path(dirpath)
        for name in filenames:
            low = name.lower()
            if "jarvis" in low:
                new_name = name
                for old, new in SPECIAL_RENAMES.items():
                    if name == old:
                        new_name = new
                        break
                else:
                    new_name = re.sub(r"jarvis", "fedex_v0", name, flags=re.I)
                    new_name = re.sub(r"JARVIS", "FEDEX_V0", new_name)
                if new_name != name:
                    renames.append((base / name, base / new_name))
        for name in dirnames:
            if "jarvis" in name.lower():
                new_name = re.sub(r"jarvis", "fedex_v0", name, flags=re.I)
                if new_name != name:
                    renames.append((base / name, base / new_name))

    # Dossiers racine prioritaires
    priority = [
        (ROOT / "src" / "jarvis", ROOT / "src" / "fedex_v0"),
        (
            ROOT / "fedex-main" / "globex-fedex-main" / "backend" / "app" / "services" / "jarvis",
            ROOT / "fedex-main" / "globex-fedex-main" / "backend" / "app" / "services" / "fedex_v0",
        ),
    ]
    for src, dst in priority:
        if src.exists() and not dst.exists():
            renames.append((src, dst))

    done = 0
    for src, dst in sorted(renames, key=lambda x: len(str(x[0])), reverse=True):
        if src.exists() and not dst.exists():
            src.rename(dst)
            done += 1
    return done


def main() -> None:
    n_content = migrate_content()
    n_rename = rename_paths()
    # Second pass after renames (paths in comments, etc.)
    n_content2 = migrate_content()
    print(f"Contenu modifié: {n_content + n_content2} fichiers")
    print(f"Renommages: {n_rename} chemins")


if __name__ == "__main__":
    main()
