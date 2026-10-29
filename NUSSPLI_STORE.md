# NUSspli addon for your existing Wii U Homebrew App Store

Adds **NUSspli** as the **second package** in your working `Morack18/wiiu-soh-store` repository. It retains the working Ship of Harkinian packaging, and uses the *exact* stable Aroma WUHB published by V10lator. No new standalone feed needs to be added to the SD card.

## Official art only

`build_nusspli.py` extracts `meta/iconTex.tga.gz` from NUSspli's **official release WUHB** and converts those exact original pixels to the `packages/nusspli/icon.png` store icon, with **no resizing, retouching, or generated graphics**. The original WUHB is installed **byte-for-byte**; that means its Wii U Menu icon, launch banner and other embedded art stay exactly as the developer supplied them. We do not inject custom graphics or change the application.

## How updates work

GitHub Actions runs on pushes, manual dispatches, and **daily at 06:12 UTC**. The NUSspli builder checks official `V10lator/NUSspli` GitHub releases, picks the highest numbered **stable** release with its matching production `NUSspli-x.yz-Aroma.zip`, verifies the GitHub-published SHA-256 (when provided), and rebuilds `public/zips/nusspli.zip` plus the feed metadata. `repo.json` exposes the exact upstream `version`. Homebrew App Store's libget compares that version with the version recorded for the installed package, and will offer **Update** when they differ and the repository has refreshed.

This **does not automatically install updates** on the console. A manually copied NUSspli WUHB won't be managed until you install/adopt it from this store once. Subsequent store updates replace only `SD:/wiiu/apps/NUSspli.wuhb`. The new upstream release must be a valid stable Aroma release in the expected format; otherwise the deployment fails safely rather than publishing a corrupt new release. Existing GitHub Pages stays at the last successfully deployed version.

## Install addon into existing Git checkout with VS Code (CachyOS)

1. Open a terminal **inside your existing local `wiiu-soh-store` checkout**, the folder containing `scripts/build_repo.py`. If you don't already have that checkout, run:

   ```bash
   git clone https://github.com/Morack18/wiiu-soh-store.git
   cd wiiu-soh-store
   ```

2. Ensure your local files are committed/saved before modifying the repo, then update it:

   ```bash
   git pull --ff-only
   cp .github/workflows/publish.yml .github/workflows/publish.yml.backup
   ```

3. Extract `wiiu-nusspli-store-addon.zip` **into that repository root**, preserving all folder paths. You can use Dolphin's Extract Here, or:

   ```bash
   unzip -o ~/Downloads/wiiu-nusspli-store-addon.zip -d .
   code .
   ```

4. The extracted files are:

   - `.github/workflows/publish.yml` — new 2-package build + auto-check schedule
   - `scripts/build_nusspli.py` — downloads and packages the official release, exports original art
   - `tests/test_nusspli.py` — eight offline tests
   - `NUSSPLI_STORE.md` — these instructions

   Do **not** replace the existing `scripts/build_repo.py`, `scripts/patch_wuhb.py`, `tests/wuhb_fixture.py`, or SoH assets: the addon uses those unchanged.

5. Run tests locally (Pillow already required by the SoH project):

   ```bash
   python3 -m unittest discover -s tests -v
   ```

6. To build and inspect the actual feed locally (requires internet access to GitHub):

   ```bash
   python3 scripts/build_repo.py --out public --compat 9.2.3
   python3 scripts/build_nusspli.py --out public
   python3 - <<'PY'
   import json
   p = json.load(open('public/repo.json'))['packages']
   print([(x['title'], x['version']) for x in p])
   PY
   ```

   Expected: `Ship of Harkinian` and `NUSspli` both present. The action performs the same build remotely.

7. Publish changes:

   ```bash
   git add .github/workflows/publish.yml scripts/build_nusspli.py tests/test_nusspli.py NUSSPLI_STORE.md
   git commit -m 'Add official NUSspli Aroma package with upstream art and automatic release checks'
   git push
   ```

8. On GitHub, go to **Actions > Publish Wii U custom Homebrew App Store**. The push should trigger the pipeline; you can run it manually too. After Pages deploys, verify:

   - `https://morack18.github.io/wiiu-soh-store/repo.json` — two entries
   - `https://morack18.github.io/wiiu-soh-store/zips/nusspli.zip` — package is downloadable
   - `https://morack18.github.io/wiiu-soh-store/packages/nusspli/icon.png` — original publisher icon

9. On the Wii U, open **Homebrew App Store** with your existing custom feed configured, refresh/reopen it, locate **NUSspli**, and install. Future versions appear as **Update** when the GitHub workflow republishes the changed version and the store refreshes.

## Important

- Only NUSspli's own Aroma homebrew WUHB is repackaged; no game content, tickets, or other Nintendo material is included.
- If GitHub Actions reports that an upstream ZIP changed format, review the NUSspli release. The script deliberately refuses to guess about new executable layout or extra executables.
- The store entry **does not** bypass Wii U system firmware requirements; the separate Breath of the Wild launch issue still needs to be diagnosed based on its exact error message.
- This addon is unofficial; the software comes from its original publisher: https://github.com/V10lator/NUSspli.
