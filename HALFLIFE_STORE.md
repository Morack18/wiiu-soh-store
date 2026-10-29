# Half-Life Wii U — custom Homebrew App Store addon

Adds one new **Half-Life (Wii U)** entry to the existing `Morack18/wiiu-soh-store` feed. Keeps Ship of Harkinian, NUSspli and Chupathingy/Warthog unchanged. Uses **official** stable releases from [NanoBunTV/Wii-U-Half-Life](https://github.com/NanoBunTV/Wii-U-Half-Life/releases), not unofficial third-party rebuilds.

## What gets installed

The one Homebrew App Store package installs **three original WUHB executables** without modification:

- `wiiu/apps/halflife.wuhb` — Half-Life
- `wiiu/apps/bshift.wuhb` — Blue Shift
- `wiiu/apps/opfor.wuhb` — Opposing Force

Each appears separately on the Wii U Menu with the **developer-supplied icon and splash screens** embedded in the original bundle. The listing icon is extracted from the official `halflife.wuhb`'s embedded icon (`meta/iconTex.tga.gz`) and losslessly converted to PNG, without redrawing or altering the original executable. Installing the package does **not** provide Valve game files.

Requires a Steam copy of Half-Life: copy its `valve` folder to `sd:/wiiu/apps/halflife/valve/`. For the expansions (if owned), copy `bshift/` and/or `gearbox/` next to `valve/`. They each need `valve/` as well. No game files, save files, settings, or engine logs are bundled or changed by the store updater.

## How auto-updates work

The existing GitHub Actions workflow runs on every push, on manual dispatch, and each day at **06:12 UTC**. It queries NanoBunTV's official published releases and chooses the numerically highest **stable** release named `vMAJOR.MINOR.PATCH` that contains `Wii-U-Half-Life-vMAJOR.MINOR.PATCH.zip`. It checks the SHA-256 release digest when GitHub provides one, validates the official executable paths, republishes a `halflife_wiiu.zip`, and exposes the upstream version in `repo.json`.

Opening/refreshing the Wii U Homebrew App Store after the new deployment should show **Update** if your previously installed store-managed version differs. Updates are **not** installed automatically. The feed's installed package manifest tracks only the three `.wuhb` files. Do not use **Uninstall** to upgrade, as uninstall removes tracked WUHB files. A manual copy before the initial App Store install won't have a store package record yet: install/adopt once from the store.

An unexpected upstream archive layout or file fails the job, so the previously successful GitHub Pages deployment should remain in place. This is intentionally safer than silently packaging unreviewed content.

## Add to existing VS Code project on CachyOS

From your **existing repository** (not `~`):

```bash
cd ~/wiiu-soh-store
git pull --ff-only
unzip -o ~/Downloads/wiiu-halflife-store-addon.zip -d .
python3 -m unittest discover -s tests -v
```

The ZIP adds:

- `scripts/build_halflife.py`
- `tests/test_halflife.py`
- `HALFLIFE_STORE.md`
- updated `.github/workflows/publish.yml` which keeps all **four** packages in the same feed.

Nothing else in the original repository should be overwritten.

### Real release test BEFORE publishing

`python3 -m unittest` only tests synthetic file layout. To test the **real upstream release**, run:

```bash
cd ~/wiiu-soh-store
python3 scripts/build_repo.py --out public --compat 9.2.3
python3 scripts/build_nusspli.py --out public
python3 scripts/build_warthog.py --out public
python3 scripts/build_halflife.py --out public
python3 - <<'PY'
import json
from pathlib import Path
repo = json.loads(Path('public/repo.json').read_text())
for p in repo['packages']:
    name = p['name']
    print(f"{p['title']}: {p['version']}")
    print('  icon:', (Path('public/packages')/name/'icon.png').is_file())
    print('  zip: ', (Path('public/zips')/(name+'.zip')).is_file())
assert len(repo['packages']) == 4
PY
```

Expected version as of October 29, 2026: Half-Life **1.0.1**. The live ZIP has not been directly inspected in our preparation environment; this test is mandatory before pushing. If it fails with unexpected archive paths, do **not** force the package or publish; review the reported paths against the developer's current release.

### Publish

After all tests **and** the real build succeed:

```bash
cd ~/wiiu-soh-store
git add .github/workflows/publish.yml scripts/build_halflife.py tests/test_halflife.py HALFLIFE_STORE.md
git commit -m "Add Half-Life Wii U port with original artwork and automatic updates"
git push origin main
```

Track deployment at https://github.com/Morack18/wiiu-soh-store/actions. After a successful four-app deploy, the same custom feed serves all four: https://morack18.github.io/wiiu-soh-store/repo.json.

## USB HDD / 5upartsd setup

You have the FAT32 partition of your USB HDD mounted on Linux as `/run/media/jordan/FD5B-51E4`. Your existing 5upartsd configuration makes that FAT32 storage visible to Aroma as `sd:/`. Use **that** location to copy the Half-Life *Steam game files* later. **Do not format** or alter the other Wii U-formatted USB partition. The Homebrew App Store package itself installs the three WUHBs through your working custom feed.

Example layout after installing the homebrew package and copying **your own** Steam data:

```
FAT32/wiiu/apps/
├── halflife.wuhb                 # homebrew store
├── bshift.wuhb                   # homebrew store
├── opfor.wuhb                    # homebrew store
└── halflife/
    ├── valve/                    # Steam Half-Life data (you copy)
    ├── bshift/                   # optional Steam Blue Shift data (you copy)
    └── gearbox/                 # optional Steam Opposing Force data (you copy)
```

Half-Life for Wii U is a single-player port supporting GamePad and Pro Controller. This package is unofficial and is not endorsed by NanoBunTV, Valve, Nintendo, or ForTheUsers. Respect the licensing terms of the upstream source and your game files.
