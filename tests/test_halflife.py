"""Offline tests for the Half-Life Wii U custom-store addon (no game data)."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import warnings
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from build_halflife import (PACKAGE, PRIMARY, FILES, build_package,
                            extract_bundles, official_icon_png,
                            safe_path, select_release)
from wuhb_fixture import make_fake_wuhb


def sample_zip(exclude=(), extra=None, doc=False, duplicate=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in FILES:
            if path not in exclude:
                z.writestr(path, make_fake_wuhb())
        if doc:
            z.writestr("README.md", b"Upstream instructions")
        if extra:
            z.writestr(extra, b"UNREVIEWED")
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                z.writestr(FILES[1], make_fake_wuhb())
    return buf.getvalue()


def sample_release(version, archive, *, prerelease=False, draft=False, tag=None):
    tag = tag or f"v{version}"
    return {
        "tag_name": tag, "name": tag,
        "draft": draft, "prerelease": prerelease,
        "published_at": "2026-10-16T02:42:41Z",
        "html_url": f"https://github.com/NanoBunTV/Wii-U-Half-Life/releases/tag/{tag}",
        "assets": [{
            "name": f"Wii-U-Half-Life-{tag}.zip",
            "browser_download_url": (
                "https://github.com/NanoBunTV/Wii-U-Half-Life/releases/download/"
                f"{tag}/Wii-U-Half-Life-{tag}.zip"
            ),
            "digest": "sha256:" + hashlib.sha256(archive).hexdigest(),
        }],
    }


def make_feed(root):
    root.mkdir(parents=True, exist_ok=True)
    original = [
        {"name": "soh_wiiu_community", "version": "9.2.3-r3-store2"},
        {"name": "nusspli", "version": "1.159"},
        {"name": "chupathingy_wiiu", "version": "test-20261027"},
    ]
    (root / "repo.json").write_text(json.dumps({"packages": original}))
    return original


class HalfLifeTests(unittest.TestCase):
    def test_select_newest_semver_stable(self):
        archive = sample_zip()
        rows = [sample_release("1.0.1", archive), sample_release("1.0.2", archive),
                sample_release("1.1.0", archive, prerelease=True),
                sample_release("2.0.0", archive, draft=True),
                sample_release("1.0.0", archive),
                sample_release("99.0.0", archive, tag="nightly")]
        rel, asset, ver = select_release(rows)
        self.assertEqual(ver, "1.0.2")
        self.assertEqual(asset["name"], "Wii-U-Half-Life-v1.0.2.zip")

    def test_current_official_release_pattern(self):
        zipbytes = sample_zip()
        release = sample_release("1.0.1", zipbytes)
        self.assertEqual(select_release([release])[2], "1.0.1")

    def test_publisher_icon_and_original_bundles(self):
        wuhb = make_fake_wuhb()
        selected = extract_bundles(sample_zip(doc=True))
        self.assertEqual(set(selected), set(FILES))
        for name in FILES:
            self.assertEqual(selected[name], wuhb)
        out = official_icon_png(selected[PRIMARY])
        with Image.open(io.BytesIO(out)) as im:
            self.assertEqual(im.size, (128, 128))
            self.assertEqual(im.convert("RGBA").getpixel((0, 0)), (255, 0, 0, 255))

    def test_four_entries_and_safe_manifest(self):
        archive = sample_zip()
        release = sample_release("1.0.1", archive)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "public"
            original = make_feed(out)
            user_data = out / "wiiu/apps/halflife/valve/save/slot1.sav"
            user_data.parent.mkdir(parents=True)
            user_data.write_bytes(b"KEEP THIS SAVE")
            cmdline = out / "wiiu/apps/halflife/cmdline.txt"
            cmdline.write_text("-log")
            feed = build_package(release, release["assets"][0], "1.0.1", archive, out)
            self.assertEqual(feed["packages"][:3], original)
            self.assertEqual([p["name"] for p in feed["packages"]],
                             [p["name"] for p in original] + [PACKAGE])
            self.assertEqual(feed["packages"][-1]["version"], "1.0.1")
            self.assertEqual(feed["packages"][-1]["binary"], PRIMARY)
            self.assertTrue((out / "packages" / PACKAGE / "icon.png").is_file())
            package_zip = out / "zips" / f"{PACKAGE}.zip"
            with zipfile.ZipFile(package_zip) as z:
                self.assertEqual(set(z.namelist()), {"info.json", "manifest.install", *FILES})
                self.assertEqual(z.read("manifest.install").decode(),
                                 "".join(f"U: {p}\n" for p in FILES))
                for path in FILES:
                    self.assertEqual(z.read(path), make_fake_wuhb())
                self.assertEqual(json.loads(z.read("info.json"))["version"], "1.0.1")
            self.assertEqual(user_data.read_bytes(), b"KEEP THIS SAVE")
            self.assertEqual(cmdline.read_text(), "-log")

    def test_new_release_updates_single_entry(self):
        a = sample_zip()
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            orig = make_feed(out)
            for ver in ("1.0.1", "1.0.2"):
                rel = sample_release(ver, a)
                feed = build_package(rel, rel["assets"][0], ver, a, out)
                self.assertEqual(len(feed["packages"]), 4)
                self.assertEqual(feed["packages"][:3], orig)
                self.assertEqual(feed["packages"][-1]["version"], ver)

    def test_checksum_mismatch(self):
        archive = sample_zip()
        rel = sample_release("1.0.1", archive)
        rel["assets"][0]["digest"] = "sha256:" + "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            make_feed(out)
            with self.assertRaisesRegex(ValueError, "SHA256"):
                build_package(rel, rel["assets"][0], "1.0.1", archive, out)

    def test_no_existing_three_app_feed(self):
        a = sample_zip()
        rel = sample_release("1.0.1", a)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Missing repo.json"):
                build_package(rel, rel["assets"][0], "1.0.1", a, Path(temp))

    def test_missing_launcher_rejected(self):
        with self.assertRaisesRegex(ValueError, "Expected three WUHBs"):
            extract_bundles(sample_zip(exclude=[FILES[2]]))

    def test_non_launcher_payload_rejected(self):
        for extra in ("wiiu/apps/halflife/valve/pak0.pak", "wiiu/apps/halflife/valve/save/slot1.sav", "wiiu/apps/halflife/cmdline.txt", "wiiu/apps/mystery.wuhb"):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError, "Unreviewed"):
                    extract_bundles(sample_zip(extra=extra))

    def test_duplicate_and_path_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            extract_bundles(sample_zip(duplicate=True))
        for path in ("../valve/pak0.pak", "/root/bad", "C:/bad", "folder\\bad", "./../bad"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    safe_path(path)

    def test_malformed_wuhb_rejected(self):
        src = io.BytesIO()
        with zipfile.ZipFile(src, "w") as z:
            for path in FILES:
                z.writestr(path, b"WRONG" * 100)
        with self.assertRaisesRegex(ValueError, "Not an Aroma WUHB"):
            extract_bundles(src.getvalue())

    def test_only_pre_or_unrecognized_releases_rejected(self):
        archive = sample_zip()
        with self.assertRaisesRegex(ValueError, "No stable"):
            select_release([sample_release("1.0.1", archive, prerelease=True),
                            sample_release("1.0.2", archive, tag="nightly")])


if __name__ == "__main__":
    unittest.main()
