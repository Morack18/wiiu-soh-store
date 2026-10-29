#!/usr/bin/env python3
"""Append a NUSspli Aroma package to the existing Wii U libget/Homebrew App Store feed.

The WUHB is copied byte-for-byte from the official V10lator/NUSspli release.
The store icon is converted pixel-for-pixel from that WUHB's embedded original
menu icon. Nothing is painted, synthesized, or patched into the WUHB.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.error
import urllib.request
import zipfile

from PIL import Image
from patch_wuhb import read_index

REPO = "V10lator/NUSspli"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
USER_AGENT = "wiiu-custom-homebrew-store-nusspli/1.0"
PACKAGE = "nusspli"
BINARY = "wiiu/apps/NUSspli.wuhb"
MAX_DOWNLOAD = 40 * 1024 * 1024
MAX_UNCOMPRESSED = 80 * 1024 * 1024
MAX_WUHB = 64 * 1024 * 1024
ALLOWED_ARCHIVE_PATHS = {"NUSspli.wuhb", "wiiu/apps/NUSspli.wuhb"}


def get_url(url: str) -> bytes:
    import os
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as res:
        length = int(res.headers.get("Content-Length") or 0)
        if length > MAX_DOWNLOAD:
            raise ValueError("Download exceeds size limit")
        payload = res.read(MAX_DOWNLOAD + 1)
    if len(payload) > MAX_DOWNLOAD:
        raise ValueError("Download exceeds size limit")
    return payload


def select_release(releases: list[dict]) -> tuple[dict, dict, str]:
    """Pick the highest numbered stable release with its exact Aroma production ZIP."""
    options = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name", "")
        matched = re.fullmatch(r"v?(\d+\.\d+(?:\.\d+)?)", tag)
        if not matched:
            continue
        version = matched.group(1)
        expected = f"NUSspli-{version}-Aroma.zip"
        matches = [a for a in release.get("assets", []) if a.get("name") == expected]
        if len(matches) != 1 or not str(matches[0].get("browser_download_url", "")).startswith(
            f"https://github.com/{REPO}/releases/download/"
        ):
            continue
        options.append((tuple(map(int, version.split("."))), release, matches[0], version))
    if not options:
        raise ValueError("No stable NUSspli release with a matching production Aroma ZIP")
    options.sort(key=lambda item: item[0], reverse=True)
    _, release, asset, version = options[0]
    return release, asset, version


def _normalize(name: str) -> str:
    if "\\" in name or ":" in name or name.startswith("/"):
        raise ValueError(f"Unsafe ZIP entry: {name!r}")
    while name.startswith("./"):
        name = name[2:]
    path = PurePosixPath(name)
    if ".." in path.parts or not name.strip():
        raise ValueError(f"Unsafe ZIP entry: {name!r}")
    return path.as_posix()


def extract_original_wuhb(archive: bytes) -> bytes:
    found = []
    unpacked = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as src:
        seen = set()
        for item in src.infolist():
            if item.is_dir():
                continue
            name = _normalize(item.filename)
            if name in seen:
                raise ValueError(f"Duplicate ZIP entry: {name}")
            seen.add(name)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Symbolic link in ZIP: {name}")
            unpacked += item.file_size
            if unpacked > MAX_UNCOMPRESSED:
                raise ValueError("Archive's uncompressed content is too large")
            if name in ALLOWED_ARCHIVE_PATHS:
                if not (80 <= item.file_size <= MAX_WUHB):
                    raise ValueError("Unexpected NUSspli.wuhb size")
                found.append(src.read(item))
            elif name.lower().endswith((".wuhb", ".rpx", ".elf")):
                raise ValueError(f"Unexpected executable in upstream ZIP: {name}")
    if len(found) != 1:
        raise ValueError(f"Expected exactly one official NUSspli.wuhb, found {len(found)}")
    if not found[0].startswith(b"WUHB"):
        raise ValueError("Invalid WUHB magic header")
    return found[0]


def original_icon_png(wuhb: bytes) -> bytes:
    """Extract publisher-supplied icon, converting TGA to PNG without resizing or redrawing."""
    _, entries = read_index(wuhb)
    _, start, size = entries["meta/iconTex.tga.gz"]
    tga = gzip.decompress(wuhb[start:start + size])
    if len(tga) > 2 * 1024 * 1024:
        raise ValueError("Embedded icon is unexpectedly large")
    with Image.open(io.BytesIO(tga)) as im:
        im.load()
        if im.size != (128, 128):
            raise ValueError(f"Unexpected upstream icon resolution: {im.size}")
        # PNG encodes precisely the same pixel data; the Wii U WUHB isn't modified.
        output = io.BytesIO()
        im.convert("RGBA").save(output, format="PNG")
        return output.getvalue()


def make_package(release: dict, asset: dict, version: str, archive: bytes, output: Path) -> dict:
    digest = str(asset.get("digest") or "")
    if digest and not digest.startswith("sha256:"):
        raise ValueError("Unsupported release digest format")
    if digest and hashlib.sha256(archive).hexdigest().lower() != digest[7:].lower():
        raise ValueError("GitHub release asset SHA256 mismatch")
    wuhb = extract_original_wuhb(archive)
    icon = original_icon_png(wuhb)

    source_url = release["html_url"]
    info = {
        "name": PACKAGE,
        "title": "NUSspli",
        "version": version,
        "author": "V10lator",
        "category": "tools",
        "description": "Install available Wii U content directly from Nintendo update servers",
        "details": ("Official NUSspli Aroma release, packaged unchanged for the Wii U "
                    "Homebrew App Store. Only NUSspli.wuhb is installed. "
                    "The icon is extracted from the official release WUHB. "
                    "The package is updated when a new stable upstream Aroma release is published."),
        "changelog": f"Official NUSspli Aroma release {version}.",
        "url": source_url,
        "license": "GPL-3.0",
    }

    if not (output / "repo.json").is_file():
        raise ValueError("Missing repo.json: build the existing Ship of Harkinian repository first")
    repo = json.loads((output / "repo.json").read_text(encoding="utf-8"))
    if not isinstance(repo.get("packages"), list):
        raise ValueError("Existing repo.json lacks a packages array")
    if any(not isinstance(pkg, dict) or "name" not in pkg for pkg in repo["packages"]):
        raise ValueError("Malformed existing package entry")

    output.joinpath("zips").mkdir(parents=True, exist_ok=True)
    output.joinpath("packages", PACKAGE).mkdir(parents=True, exist_ok=True)
    archive_out = output / "zips" / f"{PACKAGE}.zip"
    with zipfile.ZipFile(archive_out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as dest:
        dest.writestr("info.json", json.dumps(info, indent=2) + "\n")
        dest.writestr("manifest.install", f"U: {BINARY}\n")
        dest.writestr(BINARY, wuhb)
    (output / "packages" / PACKAGE / "icon.png").write_bytes(icon)

    updated_iso = release.get("published_at") or release.get("created_at")
    if not updated_iso:
        raise ValueError("Release is missing publication timestamp")
    updated = datetime.fromisoformat(updated_iso.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    entry = dict(info)
    entry.update({
        "filesize": (archive_out.stat().st_size + 999) // 1000,
        "extracted": (len(wuhb) + 999) // 1000,
        "binary": BINARY,
        "screens": 0,
        "md5": hashlib.md5(archive_out.read_bytes()).hexdigest(),
        "updated": updated,
    })
    repo["packages"] = [p for p in repo["packages"] if p["name"] != PACKAGE]
    repo["packages"].append(entry)
    (output / "repo.json").write_text(json.dumps(repo, indent=2) + "\n", encoding="utf-8")
    print(f"Added official NUSspli {version}: {archive_out.stat().st_size:,} bytes, "
          f"upstream icon, total packages: {len(repo['packages'])}")
    return repo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("public"))
    parser.add_argument("--release-json", type=Path, help="Offline test: GitHub releases JSON array")
    parser.add_argument("--asset-zip", type=Path, help="Offline test: upstream Aroma ZIP")
    args = parser.parse_args()
    if bool(args.release_json) != bool(args.asset_zip):
        parser.error("--release-json and --asset-zip must be supplied together")
    releases = (json.loads(args.release_json.read_text(encoding="utf-8"))
                if args.release_json else json.loads(get_url(RELEASES_URL)))
    release, asset, version = select_release(releases)
    archive = args.asset_zip.read_bytes() if args.asset_zip else get_url(asset["browser_download_url"])
    make_package(release, asset, version, archive, args.out)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, urllib.error.URLError, zipfile.BadZipFile,
            gzip.BadGzipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
