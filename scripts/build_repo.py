#!/usr/bin/env python3
"""Build a static libget/Homebrew App Store repository from Wii U SoH releases.

Only known executable/engine files are repackaged. Never bundle Nintendo data,
user saves, mods, settings, or other user-owned data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

REPO = "utsnik/Shipwright"
API_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
PKG = "soh_wiiu_community"
USER_AGENT = "wiiu-soh-custom-store/1.0"
# Update this compatibility family after manually testing a new base release.
DEFAULT_COMPAT = "9.2.3"
# Only package validated runtime files. Other release files are ignored or rejected.
RUNTIME_FILES = (
    "wiiu/apps/soh.wuhb",
    "wiiu/apps/soh923/soh.o2r",
)
PROHIBITED_NAMES = {"oot.o2r", "oot.otr", "oot-mq.otr"}
MAX_DOWNLOAD = 250 * 1024 * 1024
MAX_UNCOMPRESSED = 350 * 1024 * 1024


def http_read(url: str) -> bytes:
    import os
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as res:
        length = int(res.headers.get("Content-Length") or 0)
        if length > MAX_DOWNLOAD:
            raise ValueError("Release asset is too large")
        data = res.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise ValueError("Release download exceeds size limit")
        return data


def choose_release(releases: list[dict], compat: str) -> tuple[dict, dict]:
    matches = []
    pattern = re.compile(rf"^wiiu-{re.escape(compat)}-r([0-9]+)$")
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        match = pattern.fullmatch(str(rel.get("tag_name", "")))
        if not match:
            continue
        expected = f"soh-wiiu-{compat}-r{match.group(1)}.zip"
        assets = [a for a in rel.get("assets", []) if a.get("name") == expected]
        if len(assets) != 1:
            continue
        matches.append((int(match.group(1)), rel, assets[0]))
    if not matches:
        raise ValueError(f"No Wii U releases found for tested {compat} compatibility family")
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1], matches[0][2]


def normalize(name: str) -> str:
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or ":" in name:
        raise ValueError(f"Unsafe path in upstream archive: {name!r}")
    return path.as_posix()


def extract_expected(source_zip: bytes) -> dict[str, bytes]:
    selected = {}
    with zipfile.ZipFile(io.BytesIO(source_zip)) as z:
        cumulative = 0
        seen = set()
        for member in z.infolist():
            if member.is_dir():
                continue
            name = normalize(member.filename)
            if name in seen:
                raise ValueError(f"Duplicate ZIP member: {name}")
            seen.add(name)
            cumulative += member.file_size
            if cumulative > MAX_UNCOMPRESSED:
                raise ValueError("Upstream archive exceeds uncompressed size limit")
            if ((member.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError(f"Symlink not accepted: {name}")
            if PurePosixPath(name).name.lower() in PROHIBITED_NAMES:
                raise ValueError("An upstream archive unexpectedly contains copyrighted/user game data")
            if name in RUNTIME_FILES:
                selected[name] = z.read(member)
            elif name.startswith("wiiu/apps/"):
                # New runtime/config layout must be manually audited. This also
                # intentionally blocks extra code or config files from updates.
                raise ValueError(f"Unreviewed Wii U app file: {name}; release needs review")
        for required in RUNTIME_FILES:
            if required not in selected or not selected[required]:
                raise ValueError(f"Required Wii U runtime file missing: {required}")
    return selected


def build(releases: list[dict], asset_bytes: bytes, output: Path, compat: str,
          icon_path: Path) -> dict:
    release, asset = choose_release(releases, compat)
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:"):
        actual = hashlib.sha256(asset_bytes).hexdigest()
        if actual.lower() != digest[7:].lower():
            raise ValueError("Asset SHA256 does not match GitHub release metadata")
    selected = extract_expected(asset_bytes)
    version = release["tag_name"].removeprefix("wiiu-")
    title = "Ship of Harkinian (Wii U community port)"
    description = "Ocarina of Time PC port for Wii U Aroma; requires your own oot.o2r"
    shortlog = f"Wii U compatibility release {version}; see upstream release notes."
    info = {
        "name": PKG, "title": title, "version": version, "author": "HarbourMasters / utsnik",
        "category": "games", "description": description,
        "details": ("Community Wii U port for Aroma. You MUST separately make oot.o2r "
                    f"with desktop SoH {compat} and a legally dumped ROM. "
                    "Store updates replace only soh.wuhb and soh.o2r. Game data, "
                    "saves, settings, and texture mods are not part of the package. "
                    "Do not uninstall this package to perform an update."),
        "changelog": shortlog,
        "url": release["html_url"], "license": "See upstream project licenses",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "zips").mkdir(exist_ok=True)
    icon_out = output / "packages" / PKG
    icon_out.mkdir(parents=True, exist_ok=True)
    if icon_path.exists():
        shutil.copyfile(icon_path, icon_out / "icon.png")
    zip_path = output / "zips" / f"{PKG}.zip"
    manifest = "".join(f"U: {key}\n" for key in RUNTIME_FILES)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("info.json", json.dumps(info, indent=2) + "\n")
        z.writestr("manifest.install", manifest)
        for key in RUNTIME_FILES:
            z.writestr(key, selected[key])
    size = zip_path.stat().st_size
    extracted_size = sum(len(v) for v in selected.values())
    updated_iso = release.get("published_at") or datetime.now(timezone.utc).isoformat()
    updated = datetime.fromisoformat(updated_iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    entry = dict(info)
    entry.update({
        "name": PKG, "filesize": (size + 999) // 1000,
        "extracted": (extracted_size + 999) // 1000,
        "binary": "wiiu/apps/soh.wuhb", "screens": 0,
        "md5": hashlib.md5(zip_path.read_bytes()).hexdigest(), "updated": updated,
    })
    repo = {"packages": [entry]}
    (output / "repo.json").write_text(json.dumps(repo, indent=2) + "\n", encoding="utf-8")
    (output / "index.html").write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>Wii U SoH custom app repository</title><body>"
        "<h1>Wii U Ship of Harkinian repository</h1>"
        "<p>Unofficial community update feed. "
        "<a href='repo.json'>View package metadata</a>.</p></body></html>\n",
        encoding="utf-8",
    )
    (output / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built {version}: {size:,} byte package; {list(selected)}")
    return repo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("public"))
    parser.add_argument("--compat", default=DEFAULT_COMPAT,
                        help="Tested SoH base version; defaults to 9.2.3")
    parser.add_argument("--release-json", type=Path,
                        help="Offline test mode: JSON releases array")
    parser.add_argument("--asset-zip", type=Path,
                        help="Offline test mode: upstream asset ZIP")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.compat):
        parser.error("--compat must look like 9.2.3")
    if bool(args.release_json) != bool(args.asset_zip):
        parser.error("--release-json and --asset-zip must both be set or both omitted")
    if args.release_json:
        releases = json.loads(args.release_json.read_text(encoding="utf-8"))
        source = args.asset_zip.read_bytes()
    else:
        releases = json.loads(http_read(API_URL))
        _, asset = choose_release(releases, args.compat)
        source = http_read(asset["browser_download_url"])
    icon = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
    build(releases, source, args.out, args.compat, icon)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
