# Wii U Menu question-mark icon fix — store2

## Why this update exists

The prior WUHB icon patcher emitted a 128×128 32-bit TGA using a top-left origin and without a TGA 2.0 footer. The standard Wii U `wuhbtool` produces TGA data using FreeImage; the revised patcher uses Pillow's uncompressed TGA encoder for a bottom-left origin and the `TRUEVISION-XFILE` footer, then gzip-compresses the result, as the WUHB expects.

**This is a format correction and a testable hypothesis, not proof that the icon will render on real hardware.** Never assume a successful local WUHB parse guarantees the Wii U Menu will accept it.

## Changes

- Existing `assets/icon.png` remains unchanged. It supplies both the listing icon and the WUHB icon.
- `scripts/patch_wuhb.py` now emits 128×128×32-bit TGA 2.0 images, complete with 26-byte footer and conventional bottom-left origin.
- `scripts/build_repo.py` uses package version `9.2.3-r3-store2` to trigger an update for users on `store1`.
- `tests/test_wuhb.py` checks the TGA byte-level header/footer and image decode.
- `tests/test_repo.py` checks updated version metadata.

## Apply from project root in VS Code on CachyOS

Extract this patch ZIP at the root of your existing `wiiu-soh-custom-store` project, replacing matching files. Make sure your original `assets/icon.png` stays in place.

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_repo.py --out public --compat 9.2.3

git add scripts/patch_wuhb.py scripts/build_repo.py tests/test_wuhb.py tests/test_repo.py ICON_FIX_STORE2.md
git commit -m 'Fix Wii U Menu icon TGA compatibility'
git push
```

Only after GitHub Actions finishes successfully and the hosted `repo.json` reports `9.2.3-r3-store2`, update the application from Homebrew App Store. Restart the Wii U to check the Wii U Menu icon.

## Recovery fallback if the icon still renders as a question mark

The safest fallback is the **unmodified upstream Wii U WUHB**, copied to `sd:/wiiu/apps/soh.wuhb` by FTP with the app closed. The game data at `sd:/wiiu/apps/soh923/oot.o2r` is left alone. Use the URL `https://github.com/utsnik/Shipwright/releases/tag/wiiu-9.2.3-r3`, download the **normal**, not `-extras`, ZIP, extract `wiiu/apps/soh.wuhb`, and replace only that file.

A package-manager caveat: a manual FTP rollback does **not** alter the Homebrew App Store's recorded package version. Don't use the Store's uninstall option to repair the icon; that uninstalls tracked runtime files. To publish a future corrected package, increase `STORE_REVISION` again.
