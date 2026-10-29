# Chupathingy / Warthog for Wii U — Homebrew App Store addon

Adds a **third package** to your existing `Morack18/wiiu-soh-store` GitHub Pages feed. Keep your existing SoH and NUSspli scripts and tests unchanged. **Don't extract this into your home directory.** Extract from the root of the already cloned `~/wiiu-soh-store` project.

## Important: currently only upstream test releases

As of October 29, 2026, the official `ChupathingyCE/warthog-wiiu` repository has **only prerelease test builds**, the latest tagged `test-20261027` (released October 27, 2026). We support officially tagged `test-*` and `v*` GitHub releases, including prereleases, but **exclude the moving `nightly` release** to avoid unexpectedly replacing the chosen tagged build with a nightly. This is not a stable port: read the official release notes and known issues before installation.

## Official artwork and safe updates

- **Official icon only**: `build_warthog.py` extracts the developer's embedded `meta/iconTex.tga.gz` from `halo.wuhb`, converts those same pixels to the store's `packages/chupathingy_wiiu/icon.png` (PNG container conversion only, no custom design or resizing), and packages the original `halo.wuhb` unchanged along with original `halo.rpx`.
- **Install-only runtime files**: the store manifest tracks exactly `wiiu/apps/halo.wuhb` and `wiiu/apps/halo/halo.rpx`.
- **Not included / never overwritten**: `wiiu/apps/halo/maps/`, `maps_cex/`, saves, settings, cache, log files, and any other game data. Bring legitimate Halo CE NTSC (01.10.12.2276) `.map` files from your own game copy to `SD:/wiiu/apps/halo/maps/` **before launching**. Optional CE+ maps go in `maps_cex/`.
- All upstream ZIP members are inspected. Unexpected game data and files abort the build; the developer's published SHA-256 is verified when included.
- **Updates**: GitHub Actions checks on push, manual workflow dispatch and daily at 06:12 UTC. When a new official tagged test/v release is published and successfully rebuilt, its Git tag becomes the App Store package version. libget sees a changed version and can offer **Update** after refreshing the store. It does not auto-install.
- *Not affiliated with* the port authors, Microsoft, or Nintendo.

## Install the addon (VS Code, CachyOS)

1. Open the VS Code terminal, and run:

   ```bash
   cd ~/wiiu-soh-store
   git status --short
   git pull --ff-only
   unzip -o ~/Downloads/wiiu-warthog-store-addon.zip -d .
   ```

   Only the following four files are added/changed:

   ```text
   .github/workflows/publish.yml    (replace with three-app workflow)
   scripts/build_warthog.py          (new)
   tests/test_warthog.py             (new)
   WARTHOG_STORE.md                  (new)
   ```

2. Run all tests (includes the existing SoH and NUSspli tests):

   ```bash
   python3 -m unittest discover -s tests -v
   ```

3. Run an **actual** 3-package build (uses internet; tests alone do not download the upstream release):

   ```bash
   python3 scripts/build_repo.py --out public --compat 9.2.3
   python3 scripts/build_nusspli.py --out public
   python3 scripts/build_warthog.py --out public
   python3 - <<'PY'
   import json
   from pathlib import Path
   output = Path('public')
   packages = json.loads((output / 'repo.json').read_text())['packages']
   for app in packages:
       n = app['name']
       print(app['title'], app['version'],
             'ZIP', (output / 'zips' / f'{n}.zip').exists(),
             'ICON', (output / 'packages' / n / 'icon.png').exists())
   assert len(packages) == 3
   PY
   ```

   Expect Ship of Harkinian, NUSspli and Chupathingy (Wii U). If the Warthog builder rejects the official ZIP layout, **stop and inspect**; don't bypass a guard.

4. Only after the real build succeeds, publish:

   ```bash
   git add .github/workflows/publish.yml scripts/build_warthog.py tests/test_warthog.py WARTHOG_STORE.md
   git commit -m "Add Warthog Wii U with original artwork and tagged-release updates"
   git push origin main
   ```

5. On GitHub, check https://github.com/Morack18/wiiu-soh-store/actions for a green build/deploy. Then the same Homebrew App Store custom feed `https://morack18.github.io/wiiu-soh-store/` contains all three entries—no SD repository config change is needed. Open the Wii U Homebrew App Store, refresh/restart and install **Chupathingy (Wii U)**.

## Known upstream issues

The latest tagged test release notes mention online matches around 15 fps, occasional tinted effects, no movies, untested campaign, and rare dark startup screens after HOME. The GamePad and Wii U Pro Controller are reported working. Follow upstream release notes for details: https://github.com/ChupathingyCE/warthog-wiiu/releases

## Sources

- https://github.com/ChupathingyCE/warthog-wiiu
- https://github.com/ChupathingyCE/warthog-wiiu/blob/main/tools/wiiu_package.py
- https://github.com/ChupathingyCE/warthog-wiiu/blob/main/.github/workflows/release.yml
- https://github.com/fortheusers/libget
