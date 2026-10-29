# Half-Life Wii U official release path fix

Corrects the packaging path mismatch first encountered with the developer's
v1.0.1 ZIP (`wiiu/apps/halflife/bshift.wuhb`). The previous implementation
accepted only WUHBs under `wiiu/apps/` directly. It now accepts **exactly**
the three known launchers from either documented root or upstream nested
`wiiu/apps/halflife/` archive paths and installs them in the standard
Aroma menu directory (`wiiu/apps/`).

- Files inside each WUHB remain byte-for-byte identical to upstream.
- Store art still comes exclusively from the official embedded icon.
- Proprietary Valve data and unknown files still fail the build.
- Game data under `wiiu/apps/halflife/{valve,bshift,gearbox}/`, saves,
  settings and `cmdline.txt` are never packaged or overwritten.
- Future stable GitHub versions continue to update the store automatically.

## Apply

From `~/wiiu-soh-store` after your push of commit `2097a03`:

```bash
cd ~/wiiu-soh-store
git pull --ff-only
unzip -o ~/Downloads/wiiu-halflife-layout-fix.zip -d .
python3 -m unittest discover -s tests -v
python3 scripts/build_repo.py --out public --compat 9.2.3
python3 scripts/build_nusspli.py --out public
python3 scripts/build_warthog.py --out public
python3 scripts/build_halflife.py --out public
```

**Do not push if the actual upstream download reports another unreviewed
file**. Send the error, or inspect the official ZIP contents with:

```bash
curl -fL --retry 2 -o /tmp/Wii-U-Half-Life-v1.0.1.zip \
  https://github.com/NanoBunTV/Wii-U-Half-Life/releases/download/v1.0.1/Wii-U-Half-Life-v1.0.1.zip
unzip -Z1 /tmp/Wii-U-Half-Life-v1.0.1.zip
```

If all four builds succeed, publish only the fix files:

```bash
git add scripts/build_halflife.py tests/test_halflife.py HALFLIFE_LAYOUT_FIX.md
git commit -m "Fix Half-Life upstream WUHB archive layout"
git push origin main
```

The GitHub Pages deployment for commit `2097a03` failed, so the previous
successful three-app feed should remain live until this corrected workflow
deploys.
