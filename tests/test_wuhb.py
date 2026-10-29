"""Ensure our WUHB patch changes only icon data, not the executable."""
from pathlib import Path
import gzip
import io
import sys
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from patch_wuhb import read_index, patch_wuhb_bytes, icon_as_tga_gz, WuhbError
from wuhb_fixture import make_fake_wuhb


class WuhbIconTests(unittest.TestCase):
    def test_patches_only_embedded_icon_and_preserves_all_other_files(self):
        before = make_fake_wuhb()
        after = patch_wuhb_bytes(before, ROOT/'assets/icon.png')
        _, old = read_index(before)
        _, new = read_index(after)
        self.assertEqual(old.keys(), new.keys())
        for name in old:
            _, bpos, bsize = old[name]
            _, apos, asize = new[name]
            bdata = before[bpos:bpos+bsize]
            adata = after[apos:apos+asize]
            if name == 'meta/iconTex.tga.gz':
                self.assertNotEqual(bdata, adata)
                with Image.open(io.BytesIO(gzip.decompress(adata))) as icon:
                    self.assertEqual(icon.size, (128,128))
                    self.assertEqual(icon.mode, 'RGBA')
            else:
                self.assertEqual(bdata, adata, name)

    def test_icon_matches_wiiu_tga_layout(self):
        from struct import unpack_from
        compressed = icon_as_tga_gz(ROOT/'assets/icon.png')
        tga = gzip.decompress(compressed)
        self.assertEqual(tga[:4], b'\x00\x00\x02\x00')
        self.assertEqual(unpack_from('<HH', tga, 12), (128,128))
        self.assertEqual(tga[16], 32)
        # Conventional bottom-left origin, 8 bits of alpha, not top-left.
        self.assertEqual(tga[17], 8)
        self.assertEqual(len(tga), 18+128*128*4+26)
        self.assertTrue(tga.endswith(b'\x00'*8+b'TRUEVISION-XFILE.\x00'))
        with Image.open(io.BytesIO(tga)) as img:
            self.assertEqual(img.size, (128,128))
            self.assertEqual(img.mode, 'RGBA')

    def test_rejects_non_wuhb_input(self):
        with self.assertRaisesRegex(WuhbError,'WUHB'):
            patch_wuhb_bytes(b'garbage', ROOT/'assets/icon.png')

    def test_rejects_missing_icon_in_bundle(self):
        before=bytearray(make_fake_wuhb())
        # Alter the embedded icon file name to make the required path absent.
        _, files=read_index(before)
        # file table starts at header offset 56
        import struct
        filetable=struct.unpack_from('>Q',before,56)[0]
        at=filetable+files['meta/iconTex.tga.gz'][0]+32
        before[at:at+4]=b'fake'
        with self.assertRaisesRegex(WuhbError,'missing embedded icon'):
            patch_wuhb_bytes(bytes(before), ROOT/'assets/icon.png')


if __name__=='__main__':
    unittest.main()
