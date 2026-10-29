#!/usr/bin/env python3
"""Replace the embedded Wii U Menu icon in an Aroma WUHB RomFS bundle.

Based on devkitPro/wut-tools wuhbtool RomFS structures. This preserves the
original RPX and all other embedded files; it relocates the four RomFS metadata
tables and redirects only meta/iconTex.tga.gz to a new gzip-compressed TGA.

This script is independent of the Wii U Homebrew App Store listing icon.
"""
from __future__ import annotations

import gzip
import io
from pathlib import Path
import struct

from PIL import Image

HEADER = struct.Struct(">4sI9Q")
DIR = struct.Struct(">6I")
FILE = struct.Struct(">IIQQII")
EMPTY = 0xFFFFFFFF
ICON_PATH = "meta/iconTex.tga.gz"
MAX_WUHB = 200 * 1024 * 1024
MAX_ENTRIES = 10000


class WuhbError(ValueError):
    """Unexpected/malformed WUHB layout; stop rather than corrupting an app."""


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) // boundary * boundary


def icon_as_tga_gz(icon_path: Path) -> bytes:
    """Make the format consumed by the Wii U Menu: 128x128 BGRA TGA, gzip."""
    with Image.open(icon_path) as im:
        im = im.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS)
        bgra = im.tobytes("raw", "BGRA")
    # 32bit uncompressed TGA, origin top-left, 8 alpha bits per pixel.
    tga_header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, 128, 128, 32, 0x28)
    return gzip.compress(tga_header + bgra, compresslevel=9, mtime=0)


def _range(start: int, size: int, limit: int, what: str) -> None:
    if start < 0 or size < 0 or start > limit or size > limit-start:
        raise WuhbError(f"Invalid {what} range")


def read_index(blob: bytes) -> tuple[tuple[int, ...], dict[str, tuple[int,int,int]]]:
    """Index all embedded files as name => (file table offset, file data pos, size)."""
    if len(blob) < HEADER.size or len(blob) > MAX_WUHB:
        raise WuhbError("WUHB size is implausible")
    magic, header_size, dh_off, dh_len, dt_off, dt_len, fh_off, fh_len, ft_off, ft_len, part_off = HEADER.unpack_from(blob)
    fields = (dh_off, dh_len, dt_off, dt_len, fh_off, fh_len, ft_off, ft_len, part_off)
    if magic != b"WUHB" or header_size != HEADER.size or part_off != 0x200:
        raise WuhbError("Unrecognized WUHB header")
    if not (part_off < dh_off <= dt_off <= fh_off <= ft_off <= len(blob)):
        raise WuhbError("WUHB metadata offset order is invalid")
    if not (dh_off+dh_len == dt_off and dt_off+dt_len == fh_off and
            fh_off+fh_len == ft_off and ft_off+ft_len <= len(blob)):
        raise WuhbError("WUHB metadata tables are not contiguous")
    if dt_len < DIR.size:
        raise WuhbError("WUHB root directory is missing")

    found: dict[str, tuple[int,int,int]] = {}
    dir_seen: set[int] = set()
    file_seen: set[int] = set()

    def read_dir(offset: int, prefix: str, depth: int = 0) -> None:
        if offset == EMPTY:
            return
        if offset in dir_seen or depth > 64 or len(dir_seen) > MAX_ENTRIES:
            raise WuhbError("Cyclic or too-deep WUHB directory structure")
        dir_seen.add(offset)
        _range(offset, DIR.size, dt_len, "directory entry")
        parent, sibling, child, first_file, _hash, name_len = DIR.unpack_from(blob, dt_off+offset)
        if name_len > 1024:
            raise WuhbError("Unexpectedly long WUHB directory name")
        _range(offset+DIR.size, name_len, dt_len, "directory name")
        name = blob[dt_off+offset+DIR.size:dt_off+offset+DIR.size+name_len].decode("utf8")
        if "/" in name or name in (".", "..") or "\\" in name:
            raise WuhbError("Unsafe WUHB directory name")
        dirname = f"{prefix}{name}/" if name else prefix

        file_off = first_file
        while file_off != EMPTY:
            if file_off in file_seen or len(file_seen) > MAX_ENTRIES:
                raise WuhbError("Cyclic WUHB file list")
            file_seen.add(file_off)
            _range(file_off, FILE.size, ft_len, "file table entry")
            fparent, fsibling, offset_data, fsize, _hash, fname_len = FILE.unpack_from(blob, ft_off+file_off)
            if fparent != offset:
                raise WuhbError("WUHB file parent pointer mismatch")
            if fname_len > 1024:
                raise WuhbError("Unexpectedly long WUHB filename")
            _range(file_off+FILE.size, fname_len, ft_len, "filename")
            fname = blob[ft_off+file_off+FILE.size:ft_off+file_off+FILE.size+fname_len].decode("utf8")
            if "/" in fname or fname in (".", "..") or "\\" in fname:
                raise WuhbError("Unsafe WUHB filename")
            file_pos = part_off+offset_data
            _range(file_pos, fsize, dh_off, "file data")
            full = dirname+fname
            if full in found:
                raise WuhbError(f"Duplicate WUHB file {full}")
            found[full] = (file_off, file_pos, fsize)
            file_off = fsibling

        if child != EMPTY:
            read_dir(child, dirname, depth+1)
        if sibling != EMPTY:
            read_dir(sibling, prefix, depth)

    read_dir(0, "")
    if not found or ICON_PATH not in found or "code/root.rpx" not in found:
        raise WuhbError("WUHB is missing embedded icon or RPX executable")
    return fields, found


def patch_wuhb_bytes(original: bytes, icon_path: Path) -> bytes:
    """Safely patch WUHB in memory and verify all other embedded files unchanged."""
    fields, idx = read_index(original)
    dh_off, dh_len, dt_off, dt_len, fh_off, fh_len, ft_off, ft_len, part_off = fields
    entry_off, icon_pos, icon_size = idx[ICON_PATH]
    try:
        old_tga = gzip.decompress(original[icon_pos:icon_pos+icon_size])
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise WuhbError("Existing WUHB icon is not a valid gzip image") from exc
    if len(old_tga) < 18 or old_tga[2] not in (2, 10):
        raise WuhbError("Existing WUHB icon is not a TGA")
    new_icon = icon_as_tga_gz(icon_path)

    patched = bytearray(original[:dh_off])
    patched.extend(b"\0" * (align(len(patched), 16)-len(patched)))
    new_icon_off = len(patched)-part_off
    patched.extend(new_icon)
    patched.extend(b"\0" * (align(len(patched), 4)-len(patched)))
    shift = len(patched)-dh_off
    patched.extend(original[dh_off:])

    # Repoint all four metadata tables. Their contents stay byte-identical.
    for header_pos, old_pos in ((8,dh_off),(24,dt_off),(40,fh_off),(56,ft_off)):
        struct.pack_into(">Q", patched, header_pos, old_pos+shift)
    # Only update the icon file's data offset and compressed byte length.
    struct.pack_into(">QQ", patched, ft_off+shift+entry_off+8, new_icon_off, len(new_icon))

    out = bytes(patched)
    new_fields, new_index = read_index(out)
    if set(idx) != set(new_index):
        raise WuhbError("Internal validation failed: WUHB file list changed")
    for name, (_, old_pos, old_size) in idx.items():
        _, new_pos, new_size = new_index[name]
        if name == ICON_PATH:
            if out[new_pos:new_pos+new_size] != new_icon:
                raise WuhbError("Internal validation failed: icon mismatch")
        elif old_size != new_size or original[old_pos:old_pos+old_size] != out[new_pos:new_pos+new_size]:
            raise WuhbError(f"Internal validation failed: {name} changed")
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="Original upstream soh.wuhb")
    ap.add_argument("output", type=Path, help="Patched WUHB output")
    ap.add_argument("--icon", type=Path, default=Path("assets/icon.png"))
    args = ap.parse_args()
    if args.input.resolve() == args.output.resolve():
        ap.error("Input and output must differ; keep an original backup")
    result = patch_wuhb_bytes(args.input.read_bytes(), args.icon)
    args.output.write_bytes(result)
    print(f"Patched WUHB icon using {args.icon}: {args.output} ({len(result):,} bytes)")

if __name__ == "__main__":
    main()
