# Ship of Harkinian — custom Wii U Homebrew App Store repository

A **ready-to-host** independent libget package feed for the Wii U Homebrew App Store. It uses the community Wii U releases in `utsnik/Shipwright`, **not** the unrelated PC-only release ZIPs in the main HarbourMasters repository. Designed for an existing Aroma setup.

## Features

- Existing stock Homebrew App Store remains untouched; your added repo appears alongside ForTheUsers.
- GitHub Actions checks releases daily, repackages the supported Wii U release, and publishes `repo.json`, `zips/soh_wiiu_community.zip`, and the app icon to GitHub Pages.
- Updates the executable `sd:/wiiu/apps/soh.wuhb` and engine `sd:/wiiu/apps/soh923/soh.o2r` only.
- **Does not contain or modify** `oot.o2r` (you create it separately from a legally dumped Ocarina of Time ROM), existing saves, controller settings, or texture packs.
- Fails safely on unreviewed Wii U runtime paths or releases outside the tested 9.2.3 compatibility family.
- A backup is made before any `repos.json` edit.

## 1. Host on GitHub Pages

1. Create a new **public** GitHub repository named `wiiu-soh-store` in your GitHub account.
2. Upload all files **inside** this folder to the repository root, including the hidden `.github` folder. Use git from CachyOS for easiest results:

   ```bash
   cd /path/to/wiiu-soh-custom-store
   git init
   git branch -M main
   git add .
   git commit -m 'Add SoH Wii U custom Homebrew App Store repository'
   git remote add origin https://github.com/YOUR_USERNAME/wiiu-soh-store.git
   git push -u origin main
   ```

   If Git prompts for credentials, use your regular authenticated git/SSH setup or `gh auth login`.
3. On GitHub, select **Settings > Pages > Build and deployment > Source: GitHub Actions**.
4. Go to **Actions > Publish Wii U SoH App Store repository > Run workflow** (if the push run didn't already succeed).
5. Verify `https://YOUR_USERNAME.github.io/wiiu-soh-store/repo.json` shows one package and that `/zips/soh_wiiu_community.zip` downloads.

GitHub Pages URL for the repository (without `/repo.json`):

`https://YOUR_USERNAME.github.io/wiiu-soh-store`

**Not published yet:** Until the workflow is run and GitHub Pages is enabled, the URL above is an example, not a working feed.

## 2. Add the feed to your Wii U SD card

Shut down the Wii U, insert the SD card in your CachyOS machine, and check its mount path with `lsblk -f` or `findmnt`.

Run the script from the repo folder, substituting YOUR_USERNAME and your mounted SD location:

```bash
python3 scripts/add_repo_to_sd.py \
  --sd '/run/media/jordan/1704-1E11' \
  --url 'https://YOUR_USERNAME.github.io/wiiu-soh-store'
```

The script **checks that the hosted feed works before changing anything**. It then backs up the existing `sd:/wiiu/apps/appstore/.get/repos.json` and appends the custom URL to the existing list. Re-running it won't duplicate the repo. Use `--dry-run` to preview.

If the file does not yet exist, it writes a configuration containing both the official ForTheUsers repo and the custom repo. Eject the SD safely.

## 3. Install or adopt SoH from App Store

1. Open your existing Homebrew App Store on the Wii U while connected to the internet.
2. Find **Ship of Harkinian (Wii U community port)**. It will initially say *Install* even if SoH was installed manually: the store can't detect WUHB installations for this package until it has created its package manifest.
3. Select **Install once**. This adopts/overwrites only the two approved runtime files, leaving game data and saves untouched.
4. Make sure you have `sd:/wiiu/apps/soh923/oot.o2r`, created with **desktop SoH 9.2.3** and your own legally dumped ROM. The repo never provides this file. **Don't launch without it**—the Wii U port's missing-data prompt requires a power-button shutdown.
5. Launch Ship of Harkinian from the Wii U Menu. On a newer compatible r-release, the App Store will show an update when you open it. The action to update is manual, not background.

If your existing setup is the old 8.0.6/`sd:/wiiu/apps/soh/` layout, this is a newer, separate community port and **not** a transparent upgrade: prepare the 9.2.3 `oot.o2r` first. Do not assume old data files can be reused.

**Do not use App Store > Uninstall** on this package expecting to keep its executable. The U manifest correctly removes tracked executable/engine files on uninstall. It does *not* touch `oot.o2r`, saves or mods.

## Upgrades & compatibility

GitHub Actions runs daily around 06:12 UTC. It only publishes revisions matching `wiiu-9.2.3-rN` and `soh-wiiu-9.2.3-rN.zip` from [utsnik/Shipwright](https://github.com/utsnik/Shipwright/releases). This intentionally **does not automatically publish a newer major/minor desktop SoH release**: Wii U compatibility and `oot.o2r` format may change. For a future Wii U 9.3.x, first review/testing new runtime file layout, archive format and game data requirements, then change `--compat 9.2.3` in the workflow (and `RUNTIME_FILES` in the builder, if the paths changed).

Upstream GitHub publishes integrity digest for its release asset; this builder checks SHA-256 if available and refuses unknown archive paths, missing executable/asset files, or unexpected ROM/game data. If a scheduled run fails, the previously deployed Pages repository remains in service. Review its Action logs before attempting to update.

## Local tests

```bash
python3 -m unittest discover -s tests -v
```

To generate output locally if you have network access:

```bash
python3 scripts/build_repo.py --out public
python3 -m http.server 8000 --directory public
```

Feed preview at `http://localhost:8000/repo.json`. A local web server isn't accessible to the Wii U unless hosted on a reachable network address and configured into the store; GitHub Pages is recommended.

## Sources

- https://github.com/fortheusers/hb-appstore
- https://github.com/fortheusers/libget/wiki/Packages-and-Package-Structure
- https://github.com/utsnik/Shipwright/releases

Not affiliated with Nintendo, HarbourMasters, ForTheUsers, or the upstream Wii U port maintainer. No copyrighted Nintendo assets are distributed.
