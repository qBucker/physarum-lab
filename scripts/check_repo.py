#!/usr/bin/env python3
"""Repository hygiene check for the public physarum-lab tree.

Checks, without downloading Git LFS objects:
  * no absolute home paths in text files;
  * no common credential patterns;
  * every JSON file parses;
  * every data/*/meta.json host field is the publication placeholder;
  * every small file listed in a SHA256SUMS file matches its hash.

Large files and Git LFS pointer files are skipped; the LFS objects are the
commitment, not the CI copy.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "vendor", "__pycache__", ".venv", "node_modules"}
SKIP_PREFIX = "sim/results/_"
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_HASH_BYTES = 20 * 1024 * 1024
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"

PATH_PATTERNS = [
    re.compile(r"/home/[A-Za-z0-9_.-]+/"),
    re.compile(r"\\\\wsl\.localhost\\Ubuntu\\home\\"),
    re.compile(r"C:\\\\Users\\\\"),
]
SECRET_PATTERNS = [
    re.compile(r"gho_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    re.compile(r"(?i)(?:password|passwd|api[_-]?key|secret)\s*[:=]\s*['\"][^'\"]{6,}"),
]
SELF = "scripts/check_repo.py"

errors: list[str] = []
checked_text = 0
checked_json = 0
checked_sums = 0
skipped_lfs = 0


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel.startswith(SKIP_PREFIX):
            continue
        yield path, rel


def main() -> int:
    global checked_text, checked_json, checked_sums, skipped_lfs

    for path, rel in iter_files():
        if rel == SELF:
            continue
        size = path.stat().st_size
        if size > MAX_TEXT_BYTES:
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            continue
        text = data.decode("utf-8", "ignore")
        checked_text += 1
        for pat in PATH_PATTERNS:
            if pat.search(text):
                errors.append(f"{rel}: absolute home path pattern")
                break
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                errors.append(f"{rel}: possible credential pattern")
                break

    for path, rel in iter_files():
        if not rel.endswith(".json"):
            continue
        if path.stat().st_size > 5 * 1024 * 1024:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
            checked_json += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{rel}: JSON parse error: {exc}")

    for meta in sorted((ROOT / "data").glob("*/meta.json")):
        try:
            obj = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:  # already reported above
            continue
        host = obj.get("host")
        if host is not None and host != "workstation":
            errors.append(f"{meta.relative_to(ROOT).as_posix()}: "
                          f"host field is not 'workstation'")

    for sums in sorted(ROOT.rglob("SHA256SUMS")):
        if any(part in SKIP_DIRS for part in sums.parts):
            continue
        rel_dir = sums.parent.relative_to(ROOT).as_posix()
        if rel_dir.startswith(SKIP_PREFIX):
            continue
        for line in sums.read_text(encoding="utf-8").splitlines():
            if "  " not in line:
                continue
            digest, name = line.split("  ", 1)
            target = sums.parent / name
            rel_target = target.relative_to(ROOT).as_posix()
            if not target.is_file():
                errors.append(f"{rel_target}: listed in {rel_dir}/SHA256SUMS "
                              f"but missing")
                continue
            data = target.read_bytes()
            if data.startswith(LFS_POINTER):
                skipped_lfs += 1
                continue
            if len(data) > MAX_HASH_BYTES:
                continue
            if hashlib.sha256(data).hexdigest() != digest:
                errors.append(f"{rel_target}: SHA256 mismatch")
            else:
                checked_sums += 1

    print(f"text files scanned: {checked_text}")
    print(f"JSON files parsed: {checked_json}")
    print(f"SHA256 entries verified: {checked_sums} "
          f"(LFS pointers skipped: {skipped_lfs})")
    if errors:
        print("\nFAIL")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
