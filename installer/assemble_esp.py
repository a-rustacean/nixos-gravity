#!/usr/bin/env python3
"""Merge the NixOS EFI tree with Gravity's verified stage-two ZIP payload."""

import argparse
from pathlib import Path, PurePosixPath
import shutil
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

    with zipfile.ZipFile(gravity_zip) as archive:
        for name in archive.namelist():
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts:
                raise ValueError(f"unsafe path in Gravity stage-two ZIP: {name}")
        try:
            boot_bin = archive.read(STAGE2_MEMBER)
        except KeyError as error:
            raise ValueError(f"Gravity stage-two ZIP lacks {STAGE2_MEMBER}") from error

    if not boot_bin:
        raise ValueError("Gravity stage-two boot.bin is empty")

    shutil.copytree(nixos_esp, output)
    boot_path = output / "m1n1/boot.bin"
    boot_path.parent.mkdir(parents=True, exist_ok=True)
    boot_path.write_bytes(boot_bin)


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
