#!/usr/bin/env python3
"""Append NanoBunTV's official Half-Life Wii U WUHB trio to the custom store.

Ships only upstream-authored executable bundles, unchanged. Never includes
Half-Life, Blue Shift, or Opposing Force proprietary data or save files.
Run AFTER build_repo.py, build_nusspli.py, and build_warthog.py.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.request
import zipfile

from PIL import Image
from patch_wuhb import read_index

REPO = "NanoBunTV/Wii-U-Half-Life"
API_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
PACKAGE = "halflife_wiiu"
FILES = (
    "wiiu/apps/halflife.wuhb",       # Half-Life
    "wiiu/apps/bshift.wuhb",         # Blue Shift
    "wiiu/apps/opfor.wuhb",          # Opposing Force
)
PRIMARY = FILES[0]
# Official v1.0.1 release includes a WUHB inside wiiu/apps/halflife/.
# The builder's first version mistakenly assumed all three were at the root.
# Install to the standard Aroma menu paths regardless of which of these
# publisher-supplied archive layouts is used. WUHB bytes are never modified.
SOURCE_TO_DEST = {source: dest for dest in FILES for source in (
    dest,
    f"wiiu/apps/halflife/{PurePosixPath(dest).name}",
)}
MAX_DOWNLOAD = 110 * 1024 * 1024
MAX_UNCOMPRESSED = 230 * 1024 * 1024
MAX_WUHB = 85 * 1024 * 1024
MAX_ICON = 2 * 1024 * 1024
UA = "wiiu-custom-homebrew-store-halflife/1.0"
# Common harmless human-readable files may be bundled in a release; they are
# not installed or published. Any unreviewed executable/game payload stops build.
ALLOWED_DOCUMENTS = {"README.md", "README.txt", "LICENSE", "LICENSE.md"}


def http_get(url: str) -> bytes:
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
        length = int(response.headers.get("Content-Length") or 0)
        if length > MAX_DOWNLOAD:
            raise ValueError("Upstream download exceeds maximum size")
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("Upstream download exceeds maximum size")
    return data


def select_release(releases: list[dict]) -> tuple[dict, dict, str]:
    """Highest semantic-versioned stable release with its exact official ZIP."""
    matches = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or "")
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
        if not match:
            continue
        version = ".".join(match.groups())
        expected = f"Wii-U-Half-Life-{tag}.zip"
        assets = [a for a in release.get("assets", []) if a.get("name") == expected]
        if len(assets) != 1:
            continue
        asset = assets[0]
        if asset.get("browser_download_url") != f"https://github.com/{REPO}/releases/download/{tag}/{expected}":
            continue
        published = release.get("published_at")
        if not published:
            continue
        try:
            timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                continue
        except (ValueError, TypeError):
            continue
        matches.append((tuple(map(int, match.groups())), timestamp.astimezone(timezone.utc), release, asset, version))
    if not matches:
        raise ValueError("No stable official Half-Life Wii U release with expected ZIP")
    matches.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    _, _, rel, asset, version = matches[0]
    return rel, asset, version


def safe_path(name: str) -> str:
    if not name or name.startswith("/") or "\\" in name or ":" in name or "\x00" in name:
        raise ValueError(f"Unsafe ZIP entry: {name!r}")
    while name.startswith("./"):
        name = name[2:]
    path = PurePosixPath(name)
    if not path.parts or ".." in path.parts:
        raise ValueError(f"Unsafe ZIP entry: {name!r}")
    return path.as_posix()


def extract_bundles(archive: bytes) -> dict[str, bytes]:
    """Validate official root/nested WUHB layouts; map to Aroma menu paths.

    The upstream ZIP's internal directory is a source location, not the
    installation destination. Never accept or copy proprietary game data.
    """
    bundles = {}
    total = 0
    seen = set()
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        for member in source.infolist():
            path = safe_path(member.filename)
            if ((member.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError(f"Symbolic link in upstream ZIP: {path}")
            if member.is_dir():
                continue
            if path in seen:
                raise ValueError(f"Duplicate upstream ZIP entry: {path}")
            seen.add(path)
            total += member.file_size
            if total > MAX_UNCOMPRESSED:
                raise ValueError("Upstream ZIP uncompressed data too large")
            if path in SOURCE_TO_DEST:
                dest_path = SOURCE_TO_DEST[path]
                if dest_path in bundles:
                    raise ValueError(f"Duplicate Half-Life launcher at multiple archive paths: {dest_path}")
                if not (80 < member.file_size <= MAX_WUHB):
                    raise ValueError(f"Unexpected executable size: {path}")
                payload = source.read(member)
                if not payload.startswith(b"WUHB"):
                    raise ValueError(f"Not an Aroma WUHB: {path}")
                bundles[dest_path] = payload
            elif path in ALLOWED_DOCUMENTS:
                # Upstream documentation never becomes an installed file.
                if member.file_size > 2 * 1024 * 1024:
                    raise ValueError(f"Unexpected documentation size: {path}")
            else:
                raise ValueError(f"Unreviewed file or game content in upstream archive: {path}")
    if set(bundles) != set(FILES):
        raise ValueError(f"Expected three WUHBs {FILES}; found {list(bundles)}")
    return bundles


def official_icon_png(wuhb: bytes) -> bytes:
    """Store icon is a lossless PNG conversion of official embedded Menu art."""
    _, index = read_index(wuhb)
    _, offset, length = index["meta/iconTex.tga.gz"]
    if not (0 < length <= MAX_ICON):
        raise ValueError("Upstream icon size invalid")
    raw = gzip.decompress(wuhb[offset:offset + length])
    if len(raw) > MAX_ICON:
        raise ValueError("Decompressed upstream icon is too large")
    with Image.open(io.BytesIO(raw)) as img:
        img.load()
        if img.size != (128, 128):
            raise ValueError(f"Unexpected icon dimensions: {img.size}")
        output = io.BytesIO()
        img.convert("RGBA").save(output, format="PNG")
        return output.getvalue()


def build_package(release: dict, asset: dict, version: str, archive: bytes, output: Path) -> dict:
    digest = str(asset.get("digest") or "")
    if digest:
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise ValueError("Unsupported release asset digest")
        if hashlib.sha256(archive).hexdigest() != digest[7:].lower():
            raise ValueError("SHA256 mismatch for upstream release asset")
    bundles = extract_bundles(archive)
    icon = official_icon_png(bundles[PRIMARY])
    feed = output / "repo.json"
    if not feed.is_file():
        raise ValueError("Missing repo.json; build the existing three applications first")
    repo = json.loads(feed.read_text(encoding="utf-8"))
    packages = repo.get("packages")
    if not isinstance(packages, list) or any(not isinstance(e, dict) or not isinstance(e.get("name"), str) for e in packages):
        raise ValueError("Existing repo.json packages malformed")
    if len(packages) < 3:
        raise ValueError("Expected existing three-app feed before adding Half-Life")
    published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
    info = {
        "name": PACKAGE,
        "title": "Half-Life (Wii U)",
        "version": version,
        "author": "NanoBunTV / Xash3D FWGS",
        "category": "games",
        "description": "Half-Life for Aroma, plus Blue Shift and Opposing Force launchers; Steam files required",
        "details": (
            "Official Half-Life for Wii U Aroma port. Installs three separate Wii U Menu "
            "launchers: Half-Life, Blue Shift and Opposing Force, with their original icons. "
            "Requires your own current Steam Half-Life files: copy the valve directory "
            "to sd:/wiiu/apps/halflife/valve. For expansions, also copy bshift and/or "
            "gearbox directories beside valve from your own Steam installation. "
            "Supports GamePad and Pro Controller, with gyro aiming on GamePad. "
            "Store updates ONLY halflife.wuhb, bshift.wuhb and opfor.wuhb. "
            "Game files, saves, settings and cmdline.txt remain untouched. "
            "This port supports single-player, not multiplayer."
        ),
        "changelog": f"Official NanoBunTV Half-Life Wii U release v{version}; see upstream notes.",
        "url": release["html_url"],
        "license": "GPL-3.0-or-later (port); upstream third-party licenses apply",
    }
    (output / "zips").mkdir(parents=True, exist_ok=True)
    icon_dir = output / "packages" / PACKAGE
    icon_dir.mkdir(parents=True, exist_ok=True)
    target = output / "zips" / f"{PACKAGE}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as dest:
        dest.writestr("info.json", json.dumps(info, indent=2) + "\n")
        dest.writestr("manifest.install", "".join(f"U: {p}\n" for p in FILES))
        for path in FILES:
            dest.writestr(path, bundles[path])
    (icon_dir / "icon.png").write_bytes(icon)
    entry = dict(info)
    entry.update({
        "filesize": (target.stat().st_size + 999) // 1000,
        "extracted": (sum(map(len, bundles.values())) + 999) // 1000,
        "binary": PRIMARY,
        "screens": 0,
        "md5": hashlib.md5(target.read_bytes()).hexdigest(),
        "updated": published.strftime("%d/%m/%Y"),
    })
    repo["packages"] = [p for p in packages if p["name"] != PACKAGE] + [entry]
    feed.write_text(json.dumps(repo, indent=2) + "\n", encoding="utf-8")
    print(f"Added official Half-Life Wii U v{version}: {target.stat().st_size:,} bytes, "
          f"upstream icon, 3 original WUHBs, total packages: {len(repo['packages'])}")
    return repo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("public"))
    parser.add_argument("--release-json", type=Path, help="Offline test: releases JSON array")
    parser.add_argument("--asset-zip", type=Path, help="Offline test: official release ZIP")
    args = parser.parse_args()
    if bool(args.release_json) != bool(args.asset_zip):
        parser.error("--release-json and --asset-zip must be supplied together")
    releases = json.loads(args.release_json.read_text(encoding="utf-8")) if args.release_json else json.loads(http_get(API_URL))
    release, asset, version = select_release(releases)
    data = args.asset_zip.read_bytes() if args.asset_zip else http_get(asset["browser_download_url"])
    build_package(release, asset, version, data, args.out)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, urllib.error.URLError,
            zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
