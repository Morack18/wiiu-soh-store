# Store title + Wii U Menu icon upgrade

This upgrade changes the Homebrew App Store package title to **Ship of Harkinian** and embeds **your existing `assets/icon.png`** into the WUHB displayed on the Wii U Menu.

## Apply to the existing VS Code project

Extract the upgrade ZIP *over your repository root*. It contains only source files and tests, **not a replacement icon**. Keep your own `assets/icon.png` as-is.

On CachyOS, from the repository root:

```bash
sudo pacman -S --needed python-pillow
python3 -m unittest discover -s tests -v
python3 scripts/build_repo.py --out public --compat 9.2.3
```

**Do not push if the live `build_repo.py` command fails.** If successful, the resulting `public/zips/soh_wiiu_community.zip` contains a customized `wiiu/apps/soh.wuhb` and the original `soh.o2r`. It contains no Nintendo ROM or `oot.o2r`.

Review and push:

```bash
git status --short
git add scripts/build_repo.py scripts/patch_wuhb.py tests/test_repo.py tests/test_wuhb.py tests/wuhb_fixture.py .github/workflows/publish.yml ICON_UPGRADE.md
git commit -m "Embed custom Ship of Harkinian Wii U Menu icon"
git push
```

The CI workflow now installs Python Pillow, runs unit tests, fetches and verifies the upstream release, patches its embedded icon, and publishes the new App Store feed. If it succeeds, restart Homebrew App Store and choose **Update** for Ship of Harkinian. Exit to Wii U Menu and reboot if the old icon remains cached.

## Update detection

The original package version was `9.2.3-r3`. This customization publishes `9.2.3-r3-store1` so the App Store recognizes it as an update rather than assuming nothing changed. Future upstream `rN` releases retain the `-store1` suffix. Increment `STORE_REVISION` in `scripts/build_repo.py` if changing your bundled artwork again without a new upstream release.

## Implementation and safety

- App Store listing: `assets/icon.png` copied to `packages/soh_wiiu_community/icon.png`.
- Wii U Menu: the same PNG resized to 128x128, encoded as a gzip-compressed TGA in `meta/iconTex.tga.gz` inside `soh.wuhb`.
- The RPX executable, splash art, and any other embedded data are preserved byte-for-byte and validated.
- The patcher rejects unexpected WUHB structures and doesn't touch `oot.o2r`, save data, or mods.
- This was tested locally on a **synthetic WUHB format fixture**. The real upstream WUHB must still pass the live-build check above and be launched on Wii U before treating this as fully validated. Keep a backup of your original `soh.wuhb`.

Implementation uses the WUHB RomFS metadata structure from devkitPro/wut-tools `wuhbtool`.
