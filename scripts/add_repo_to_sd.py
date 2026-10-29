#!/usr/bin/env python3
"""Safely append a custom libget repository to a mounted Wii U SD card."""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
from urllib.parse import urlparse

DEFAULT_OFFICIAL = {
    "name": "Wii U ForTheUsers",
    "url": "https://wiiu.cdn.fortheusers.org",
    "type": "get", "enabled": True,
}


def read_remote(url: str) -> None:
    request = urllib.request.Request(url + "/repo.json", headers={"User-Agent": "WiiUSoHRepoSetup/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        j = json.load(response)
        if not isinstance(j.get("packages"), list) or not any(
            p.get("name") == "soh_wiiu_community" for p in j["packages"]
        ):
            raise ValueError("URL does not contain the expected SoH repository")


def install(sd: Path, url: str, verify: bool = True, dry_run: bool = False) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or url.endswith("repo.json"):
        raise ValueError("Use the HTTPS repository directory URL, not the repo.json file")
    url = url.rstrip("/")
    app = sd / "wiiu/apps/appstore"
    if not app.is_dir():
        raise ValueError(f"Homebrew App Store directory not found: {app}; check mounted SD path")
    cfgdir = app / ".get"
    cfg = cfgdir / "repos.json"
    if verify:
        read_remote(url)
    if cfg.exists():
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("repos"), list):
            raise ValueError("Existing repos.json not recognized; no changes made")
    else:
        data = {"repos": [DEFAULT_OFFICIAL.copy()]}
    ours = {"name": "SoH Wii U Community Updates", "url": url,
            "type": "get", "enabled": True}
    existing = next((r for r in data["repos"] if isinstance(r, dict) and r.get("url", "").rstrip("/") == url), None)
    if existing:
        print("Custom repo already present; leaving current configuration unchanged.")
        return cfg
    data["repos"].append(ours)
    print(json.dumps(data, indent=2))
    if dry_run:
        print("Dry run; SD not modified.")
        return cfg
    cfgdir.mkdir(parents=True, exist_ok=True)
    if cfg.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = cfg.with_name(f"repos.json.backup-{timestamp}")
        shutil.copy2(cfg, backup)
        print(f"Backup saved: {backup}")
    fd, temp = tempfile.mkstemp(prefix="repos-", suffix=".json", dir=cfgdir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, cfg)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print(f"Added new repo to {cfg}")
    return cfg


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sd", required=True, type=Path, help="Mounted SD card root")
    p.add_argument("--url", required=True, help="HTTPS custom repo directory, e.g. GitHub Pages site")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-verify", action="store_true", help="For local/offline testing only")
    a = p.parse_args()
    install(a.sd, a.url, verify=not a.skip_verify, dry_run=a.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
