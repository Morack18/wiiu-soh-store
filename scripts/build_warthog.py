#!/usr/bin/env python3
"""Append the official Chupathingy / Warthog Wii U Aroma port to a libget feed.

The upstream project currently publishes only tagged *prerelease* test builds.
This builder intentionally accepts tagged test/v releases, but NOT rolling
nightlies, drafts, unknown asset names, or unexpected SD-card content.
It installs just two developer-supplied binaries, preserving user maps,
configuration, saves, caches, and logs during updates.

Run after build_repo.py and build_nusspli.py:
    python3 scripts/build_warthog.py --out public
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

REPO = "ChupathingyCE/warthog-wiiu"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
PACKAGE = "chupathingy_wiiu"
APP_TITLE = "Chupathingy (Wii U)"
BINARY = "wiiu/apps/halo.wuhb"
RPX = "wiiu/apps/halo/halo.rpx"
RUNTIME_FILES = (BINARY, RPX)
USER_AGENT = "wiiu-custom-homebrew-store-warthog/1.0"
MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_UNCOMPRESSED = 160 * 1024 * 1024
MAX_RUNTIME_FILE = 90 * 1024 * 1024
MAX_ICON_TGA = 2 * 1024 * 1024


def get_url(url: str) -> bytes:
    import os
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if url.startswith("https://api.github.com/") and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as response:
        size = int(response.headers.get("Content-Length") or 0)
        if size > MAX_DOWNLOAD:
            raise ValueError("Upstream download exceeds size limit")
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("Upstream download exceeds size limit")
    return data


def select_release(releases: list[dict]) -> tuple[dict, dict, str]:
    """Choose newest *published* tagged test/v release; exclude rolling nightly.

    GitHub may show these as prereleases. Test builds are all the upstream
    offers; don't mistakenly filter them out as we do for stable NUSspli.
    """
    choices: list[tuple[datetime, int, dict, dict, str]] = []
    for release in releases:
        if release.get("draft"):
            continue
        tag = str(release.get("tag_name") or "")
        # Tag naming defined by the upstream release.yml; no nightly tracking.
        if not re.fullmatch(r"(?:test-[A-Za-z0-9][A-Za-z0-9._-]*|v[0-9][A-Za-z0-9._-]*)", tag):
            continue
        expected = f"chupathingy-wiiu-{tag}.zip"
        matches = [a for a in release.get("assets", []) if a.get("name") == expected]
        if len(matches) != 1:
            continue
        asset = matches[0]
        expected_url = f"https://github.com/{REPO}/releases/download/{tag}/{expected}"
        if asset.get("browser_download_url") != expected_url:
            continue
        published = release.get("published_at")
        if not published:
            continue
        try:
            stamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                continue
        except (TypeError, ValueError):
            continue
        choices.append((stamp.astimezone(timezone.utc), int(release.get("id") or 0),
                        release, asset, tag))
    if not choices:
        raise ValueError("No usable tagged Warthog Wii U test/v release (rolling nightlies excluded)")
    choices.sort(key=lambda v: (v[0], v[1]), reverse=True)
    _, _, release, asset, tag = choices[0]
    return release, asset, tag


def _safe_name(name: str) -> str:
    if not name or name.startswith("/") or "\\" in name or ":" in name or "\x00" in name:
        raise ValueError(f"Unsafe upstream ZIP path: {name!r}")
    while name.startswith("./"):
        name = name[2:]
    path = PurePosixPath(name)
    if ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe upstream ZIP path: {name!r}")
    return path.as_posix()


def extract_runtime(archive: bytes) -> dict[str, bytes]:
    """Reject *any* unknown content so maps/private data cannot leak into feed."""
    selected: dict[str, bytes] = {}
    unpacked = 0
    try:
        src = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise ValueError("Upstream release asset is not a ZIP") from exc
    with src:
        seen: set[str] = set()
        for member in src.infolist():
            name = _safe_name(member.filename)
            if ((member.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError(f"Symlink in upstream ZIP: {name}")
            if member.is_dir():
                continue
            if name in seen:
                raise ValueError(f"Duplicate upstream ZIP path: {name}")
            seen.add(name)
            unpacked += member.file_size
            if unpacked > MAX_UNCOMPRESSED:
                raise ValueError("Upstream ZIP exceeds uncompressed size limit")
            if name not in RUNTIME_FILES:
                raise ValueError(f"Unexpected upstream file (or potential user game data): {name}")
            if not (0 < member.file_size <= MAX_RUNTIME_FILE):
                raise ValueError(f"Invalid runtime file size: {name}")
            selected[name] = src.read(member)
    if set(selected) != set(RUNTIME_FILES):
        raise ValueError(f"Release must contain exactly {RUNTIME_FILES}; found {list(selected)}")
    if selected[BINARY][:4] != b"WUHB":
        raise ValueError("Official halo.wuhb has invalid magic")
    if selected[RPX][:4] not in (b"RPL\x00", b"\x7fELF"):
        # WUT RPX files use a standard ELF header. Some tool versions emit RPL.
        raise ValueError("Official halo.rpx does not look like RPX/ELF")
    return selected


def original_icon_png(wuhb: bytes) -> bytes:
    """Convert the upstream embedded Wii U icon to PNG; no image generation."""
    _, entries = read_index(wuhb)
    if "meta/iconTex.tga.gz" not in entries:
        raise ValueError("Official WUHB has no embedded icon")
    _, start, size = entries["meta/iconTex.tga.gz"]
    if not (0 < size <= MAX_ICON_TGA):
        raise ValueError("Official embedded icon is too large")
    tga = gzip.decompress(wuhb[start:start + size])
    if len(tga) > MAX_ICON_TGA:
        raise ValueError("Decompressed official icon is too large")
    with Image.open(io.BytesIO(tga)) as image:
        image.load()
        if image.size != (128, 128):
            raise ValueError(f"Unexpected upstream icon size: {image.size}")
        buffer = io.BytesIO()
        image.convert("RGBA").save(buffer, format="PNG")
        return buffer.getvalue()


def make_package(release: dict, asset: dict, tag: str, archive: bytes,
                 output: Path) -> dict:
    digest = str(asset.get("digest") or "")
    if digest:
        if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise ValueError("Unsupported release asset digest")
        if hashlib.sha256(archive).hexdigest() != digest[7:].lower():
            raise ValueError("Upstream ZIP SHA256 mismatch")
    runtime = extract_runtime(archive)
    icon = original_icon_png(runtime[BINARY])

    repo_file = output / "repo.json"
    if not repo_file.is_file():
        raise ValueError("Missing repo.json; build SoH and NUSspli before Warthog")
    repo = json.loads(repo_file.read_text(encoding="utf-8"))
    packages = repo.get("packages")
    if not isinstance(packages, list) or not all(
        isinstance(p, dict) and isinstance(p.get("name"), str) for p in packages
    ):
        raise ValueError("Invalid existing repo.json packages")
    stamp = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
    info = {
        "name": PACKAGE,
        "title": APP_TITLE,
        "version": tag,
        "author": "ChupathingyCE",
        "category": "games",
        "description": "Halo CE engine port for Wii U Aroma; requires your own Halo CE maps",
        "details": (
            "Official tagged Warthog/Chupathingy Wii U test release. "
            "Early test software: issues with online frame pacing, video effects and "
            "campaign support are documented upstream. Requires Aroma. "
            "Copy NTSC Halo CE (01.10.12.2276) map files from your own copy to "
            "SD:/wiiu/apps/halo/maps/. Optional CE+ maps belong in "
            "SD:/wiiu/apps/halo/maps_cex/. Game maps are NOT included. "
            "Store installs and updates only halo.wuhb and halo/halo.rpx; "
            "existing maps, saves, settings, caches and logs are not touched. "
            "Tagged test/v releases are tracked; rolling nightly builds are excluded."
        ),
        "changelog": f"Official tagged Wii U release {tag}; see upstream release notes.",
        "url": release["html_url"],
        "license": "GPL-3.0",
    }
    output.joinpath("zips").mkdir(parents=True, exist_ok=True)
    (output / "packages" / PACKAGE).mkdir(parents=True, exist_ok=True)
    zip_out = output / "zips" / f"{PACKAGE}.zip"
    # Use the official WUHB exactly as published, including its Menu icon/art.
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("info.json", json.dumps(info, indent=2) + "\n")
        z.writestr("manifest.install", "".join(f"U: {p}\n" for p in RUNTIME_FILES))
        for path in RUNTIME_FILES:
            z.writestr(path, runtime[path])
    (output / "packages" / PACKAGE / "icon.png").write_bytes(icon)
    entry = dict(info)
    entry.update({
        "filesize": (zip_out.stat().st_size + 999) // 1000,
        "extracted": (sum(map(len, runtime.values())) + 999) // 1000,
        "binary": BINARY,
        "screens": 0,
        "md5": hashlib.md5(zip_out.read_bytes()).hexdigest(),
        "updated": stamp.strftime("%d/%m/%Y"),
    })
    repo["packages"] = [p for p in packages if p["name"] != PACKAGE] + [entry]
    repo_file.write_text(json.dumps(repo, indent=2) + "\n", encoding="utf-8")
    print(f"Added official Chupathingy/Warthog {tag}: {zip_out.stat().st_size:,} "
          f"bytes, publisher icon, total packages: {len(repo['packages'])}")
    return repo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("public"))
    parser.add_argument("--release-json", type=Path, help="Offline test releases JSON")
    parser.add_argument("--asset-zip", type=Path, help="Offline test official ZIP")
    args = parser.parse_args()
    if bool(args.release_json) != bool(args.asset_zip):
        parser.error("--release-json and --asset-zip must both be specified")
    releases = json.loads(args.release_json.read_text(encoding="utf-8")) if args.release_json else json.loads(get_url(RELEASES_URL))
    release, asset, tag = select_release(releases)
    archive = args.asset_zip.read_bytes() if args.asset_zip else get_url(asset["browser_download_url"])
    make_package(release, asset, tag, archive, args.out)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, urllib.error.URLError,
            zipfile.BadZipFile, gzip.BadGzipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
