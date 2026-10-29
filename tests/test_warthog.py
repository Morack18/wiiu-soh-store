"""Offline packaging tests. Run from repository root with unittest discover."""
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

from build_warthog import (BINARY, RPX, PACKAGE, extract_runtime,
                           original_icon_png, make_package, select_release)
from wuhb_fixture import make_fake_wuhb

RPX_DATA = b"\x7fELF" + b"ORIGINAL WIIU RPX" * 192


def upstream_zip(extra=None, missing=None, wuhb=None, rpx=RPX_DATA):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if missing != BINARY:
            z.writestr(BINARY, make_fake_wuhb() if wuhb is None else wuhb)
        if missing != RPX:
            z.writestr(RPX, rpx)
        if extra:
            z.writestr(extra, b"unapproved")
    return out.getvalue()


def release(tag, blob, published="2026-10-27T20:55:34Z", prerelease=True, draft=False):
    name = f"chupathingy-wiiu-{tag}.zip"
    return {"id": 100, "tag_name": tag, "prerelease": prerelease,
            "draft": draft, "published_at": published,
            "html_url": f"https://github.com/ChupathingyCE/warthog-wiiu/releases/tag/{tag}",
            "assets": [{"name": name,
                        "browser_download_url": f"https://github.com/ChupathingyCE/warthog-wiiu/releases/download/{tag}/{name}",
                        "digest": "sha256:" + hashlib.sha256(blob).hexdigest()}]}


class WarthogTests(unittest.TestCase):
    def test_selects_newest_tagged_prerelease_not_rolling_nightly(self):
        blob = upstream_zip()
        releases = [release("test-20261024", blob, "2026-10-24T20:00:00Z"),
                    release("nightly", blob, "2026-10-29T01:00:00Z"),
                    release("test-20261027", blob, "2026-10-27T20:55:34Z"),
                    release("v9.0", blob, "2026-10-21T20:00:00Z", prerelease=False)]
        self.assertEqual(select_release(releases)[2], "test-20261027")

    def test_future_new_tag_is_seen_as_update(self):
        blob = upstream_zip()
        releases = [release("test-20261027", blob, "2026-10-27T00:00:00Z"),
                    release("v0.9.1", blob, "2026-10-30T00:00:00Z")]
        self.assertEqual(select_release(releases)[2], "v0.9.1")

    def test_rejects_unknown_release_or_missing_asset(self):
        blob = upstream_zip()
        nightly = release("nightly", blob)
        with self.assertRaisesRegex(ValueError, "No usable tagged"):
            select_release([nightly])
        test = release("test-20261027", blob)
        test["assets"][0]["name"] = "unexpected.zip"
        with self.assertRaisesRegex(ValueError, "No usable tagged"):
            select_release([test])
        draft = release("test-20261028", blob, draft=True)
        with self.assertRaisesRegex(ValueError, "No usable tagged"):
            select_release([draft])

    def test_extracts_only_unchanged_runtime(self):
        blob = upstream_zip()
        files = extract_runtime(blob)
        self.assertEqual(set(files), {BINARY, RPX})
        self.assertEqual(files[BINARY], make_fake_wuhb())
        self.assertEqual(files[RPX], RPX_DATA)

    def test_uses_publisher_embedded_icon_pixels(self):
        original = make_fake_wuhb()
        png = original_icon_png(original)
        with Image.open(io.BytesIO(png)) as image:
            self.assertEqual(image.size, (128, 128))
            self.assertEqual(image.convert('RGBA').getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(extract_runtime(upstream_zip())[BINARY], original)

    def test_rejects_game_maps_and_unreviewed_content(self):
        for extra in ("wiiu/apps/halo/maps/ui.map", "wiiu/apps/halo/maps_cex/a.map",
                      "wiiu/apps/halo/settings.ini", "wiiu/apps/other.wuhb", "evil.rpx"):
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "Unexpected upstream file"):
                extract_runtime(upstream_zip(extra=extra))

    def test_rejects_unsafe_paths_and_duplicate_entries(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            extract_runtime(upstream_zip(extra="../maps/ui.map"))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr(BINARY, make_fake_wuhb())
            z.writestr(RPX, RPX_DATA)
            z.writestr(RPX, RPX_DATA)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            extract_runtime(out.getvalue())

    def test_rejects_missing_and_bad_runtime_files(self):
        with self.assertRaisesRegex(ValueError, "must contain exactly"):
            extract_runtime(upstream_zip(missing=BINARY))
        with self.assertRaisesRegex(ValueError, "does not look like"):
            extract_runtime(upstream_zip(rpx=b"bad rpx"))
        with self.assertRaisesRegex(ValueError, "invalid magic"):
            extract_runtime(upstream_zip(wuhb=b"bad wuhb"))

    def test_build_three_packages_preserves_existing_entries_and_user_files(self):
        blob = upstream_zip()
        upstream = release("test-20261027", blob)
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            existing = [
                {"name": "soh_wiiu_community", "version": "9.2.3-r3-store2"},
                {"name": "nusspli", "version": "1.159"}
            ]
            (folder / "repo.json").write_text(json.dumps({"packages": existing}))
            maps = folder / "wiiu/apps/halo/maps/ui.map"
            maps.parent.mkdir(parents=True)
            maps.write_bytes(b"PERSONAL GAME DATA - DON'T TOUCH")
            repo = make_package(upstream, upstream["assets"][0], "test-20261027", blob, folder)
            self.assertEqual(repo["packages"][:2], existing)
            self.assertEqual(len(repo["packages"]), 3)
            self.assertEqual(repo["packages"][-1]["version"], "test-20261027")
            self.assertEqual(repo["packages"][-1]["binary"], BINARY)
            self.assertTrue((folder / "packages" / PACKAGE / "icon.png").exists())
            self.assertEqual(maps.read_bytes(), b"PERSONAL GAME DATA - DON'T TOUCH")
            with zipfile.ZipFile(folder / "zips" / f"{PACKAGE}.zip") as z:
                self.assertEqual(set(z.namelist()), {"info.json", "manifest.install", BINARY, RPX})
                self.assertEqual(z.read(BINARY), make_fake_wuhb())
                self.assertEqual(z.read(RPX), RPX_DATA)
                self.assertEqual(z.read("manifest.install").decode(), f"U: {BINARY}\nU: {RPX}\n")
                self.assertNotIn("maps", " ".join(z.namelist()))
            later = release("test-20261028", blob, "2026-10-28T20:55:34Z")
            repo = make_package(later, later["assets"][0], "test-20261028", blob, folder)
            self.assertEqual(len(repo["packages"]), 3)
            self.assertEqual(repo["packages"][-1]["version"], "test-20261028")
            self.assertEqual(maps.read_bytes(), b"PERSONAL GAME DATA - DON'T TOUCH")

    def test_rejects_tampered_download_and_missing_existing_feed(self):
        blob = upstream_zip()
        upstream = release("test-20261027", blob)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "repo.json").write_text('{"packages": []}')
            with self.assertRaisesRegex(ValueError, "SHA256"):
                make_package(upstream, upstream["assets"][0], "test-20261027", blob + b"TAMPER", out)
            (out / "repo.json").unlink()
            with self.assertRaisesRegex(ValueError, "Missing repo.json"):
                make_package(upstream, upstream["assets"][0], "test-20261027", blob, out)


if __name__ == "__main__":
    unittest.main()
