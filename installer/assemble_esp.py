#!/usr/bin/env python3
"""Merge the NixOS EFI tree with Gravity's verified stage-two ZIP payload."""

import argparse
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


REQUIRED_FILES = (
    "EFI/BOOT/BOOTAA64.EFI",
    "EFI/Linux/nixos-gravity.efi",
    "loader/loader.conf",
    "loader/entries/nixos-gravity.conf",
)
STAGE2_MEMBER = "esp/m1n1/boot.bin"


def assemble(nixos_esp: Path, gravity_zip: Path, output: Path) -> None:
    for relative in REQUIRED_FILES:
        if not (nixos_esp / relative).is_file():
            raise ValueError(f"NixOS ESP is missing {relative}")

    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")

    stage_files: list[tuple[PurePosixPath, bytes]] = []
    seen: set[PurePosixPath] = set()
    with zipfile.ZipFile(gravity_zip) as archive:
        for info in archive.infolist():
            name = info.filename
            member = PurePosixPath(name)
            if "\\" in name or member.is_absolute() or ".." in member.parts:
                raise ValueError(f"unsafe path in Gravity stage-two ZIP: {name}")
            if not member.parts or member.parts[0] != "esp" or info.is_dir():
                continue
            relative = PurePosixPath(*member.parts[1:])
            if not relative.parts:
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"symlink in Gravity stage-two ZIP is not allowed: {name}")
            if relative in seen:
                raise ValueError(f"duplicate ESP path in Gravity stage-two ZIP: {relative}")
            seen.add(relative)
            stage_files.append((relative, archive.read(info)))

    if PurePosixPath("m1n1/boot.bin") not in seen:
        raise ValueError(f"Gravity stage-two ZIP lacks {STAGE2_MEMBER}")

    boot_bin = next(data for path, data in stage_files if path == PurePosixPath("m1n1/boot.bin"))
    if not boot_bin:
        raise ValueError("Gravity stage-two boot.bin is empty")

    shutil.copytree(nixos_esp, output)
    for relative, data in stage_files:
        destination = output.joinpath(*relative.parts)
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"Gravity stage-two file would overwrite NixOS ESP content: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nixos_esp", type=Path)
    parser.add_argument("gravity_stage2_zip", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    assemble(args.nixos_esp, args.gravity_stage2_zip, args.output)
    print(f"assembled NixOS ESP + Gravity stage 2 at {args.output}")


if __name__ == "__main__":
    main()
