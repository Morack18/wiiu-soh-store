"""Offline unit tests for the NUSspli addon to wiiu-soh-store.

Run from the existing repo root: python3 -m unittest discover -s tests -v
Uses the repository's existing synthetic WUHB fixture (no Nintendo content).
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from build_nusspli import (BINARY, PACKAGE, extract_original_wuhb, make_package,
                           original_icon_png, select_release)
from wuhb_fixture import make_fake_wuhb


def official_like_zip(wuhb=None, extra=None, filename="NUSspli.wuhb"):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename, make_fake_wuhb() if wuhb is None else wuhb)
        z.writestr("README.txt", b"Upstream README")
        if extra:
            z.writestr(extra, b"SURPRISE")
    return target.getvalue()


def release_for(version, archive, prerelease=False):
    return {
        "tag_name": f"v{version}",
        "draft": False, "prerelease": prerelease,
        "html_url": f"https://github.com/V10lator/NUSspli/releases/tag/v{version}",
        "published_at": "2026-10-05T17:39:44Z",
        "assets": [{
            "name": f"NUSspli-{version}-Aroma.zip",
            "browser_download_url": f"https://github.com/V10lator/NUSspli/releases/download/v{version}/NUSspli-{version}-Aroma.zip",
            "digest": "sha256:" + hashlib.sha256(archive).hexdigest(),
        }]
    }


class NusspliPackagingTests(unittest.TestCase):
    def test_selects_latest_stable_production_aroma(self):
        blob = official_like_zip()
        rels = [release_for("1.159", blob), release_for("1.161", blob, prerelease=True),
                release_for("1.160", blob)]
        release, asset, version = select_release(rels)
        self.assertEqual(version, "1.160")
        self.assertEqual(asset["name"], "NUSspli-1.160-Aroma.zip")

    def test_official_icon_pixels_and_wuhb_unchanged(self):
        original = make_fake_wuhb()
        png = original_icon_png(original)
        with Image.open(io.BytesIO(png)) as icon:
            self.assertEqual(icon.size, (128, 128))
            self.assertEqual(icon.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(extract_original_wuhb(official_like_zip(original)), original)

    def test_feed_contains_both_apps_and_updates_existing_nusspli(self):
        blob = official_like_zip()
        with tempfile.TemporaryDirectory() as temp:
            public = Path(temp) / "public"
            public.mkdir()
            soh = {"name": "soh_wiiu_community", "version": "9.2.3-r3-store2"}
            (public / "repo.json").write_text(json.dumps({"packages": [soh]}))
            first = release_for("1.159", blob)
            repo = make_package(first, first["assets"][0], "1.159", blob, public)
            self.assertEqual(len(repo["packages"]), 2)
            self.assertEqual(repo["packages"][0], soh)
            self.assertEqual(repo["packages"][1]["binary"], BINARY)
            self.assertEqual(repo["packages"][1]["version"], "1.159")
            self.assertTrue((public / "packages" / PACKAGE / "icon.png").is_file())
            with zipfile.ZipFile(public / "zips" / "nusspli.zip") as z:
                self.assertEqual(set(z.namelist()), {"info.json", "manifest.install", BINARY})
                self.assertEqual(z.read(BINARY), make_fake_wuhb())
                self.assertEqual(z.read("manifest.install"), f"U: {BINARY}\n".encode())
                self.assertEqual(json.loads(z.read("info.json"))["version"], "1.159")
            later = release_for("1.160", blob)
            second = make_package(later, later["assets"][0], "1.160", blob, public)
            self.assertEqual(len(second["packages"]), 2)
            self.assertEqual(second["packages"][0], soh)
            self.assertEqual(second["packages"][1]["version"], "1.160")

    def test_bad_digest_rejected(self):
        blob = official_like_zip()
        rel = release_for("1.159", blob)
        rel["assets"][0]["digest"] = "sha256:" + "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "repo.json").write_text('{"packages":[]}')
            with self.assertRaisesRegex(ValueError, "SHA256"):
                make_package(rel, rel["assets"][0], "1.159", blob, out)

    def test_rejects_unexpected_executables(self):
        with self.assertRaisesRegex(ValueError, "Unexpected executable"):
            extract_original_wuhb(official_like_zip(extra="Bad.rpx"))

    def test_rejects_bad_or_multiple_wuhb(self):
        with self.assertRaisesRegex(ValueError, "Invalid WUHB"):
            extract_original_wuhb(official_like_zip(wuhb=b"A" * 100))
        with self.assertRaisesRegex(ValueError, "Unexpected executable"):
            extract_original_wuhb(official_like_zip(filename="something_else.wuhb"))

    def test_rejects_prereleases_only(self):
        blob = official_like_zip()
        with self.assertRaisesRegex(ValueError, "No stable"):
            select_release([release_for("1.160", blob, prerelease=True)])

    def test_requires_existing_feed(self):
        blob = official_like_zip()
        rel = release_for("1.159", blob)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Missing repo.json"):
                make_package(rel, rel["assets"][0], "1.159", blob, Path(temp))


if __name__ == "__main__":
    unittest.main()
