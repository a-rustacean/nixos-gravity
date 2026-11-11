#!/usr/bin/env python3
"""Create the ZIP package consumed by Gravity's OSInstaller."""

import argparse
import json
from pathlib import Path
import tempfile
import zipfile

from assemble_esp import assemble


HERE = Path(__file__).resolve().parent
BOOT_SOURCES = HERE / "boot-sources.json"
INSTALLER_DATA = HERE / "installer_data.json"


def make_package(nixos_esp: Path, gravity_stage2_zip: Path, root_image: Path, output: Path) -> None:
    if not root_image.is_file():
        raise ValueError(f"root image does not exist: {root_image}")
    image_size = root_image.stat().st_size
    if image_size == 0 or image_size % 4096:
        raise ValueError("root image must be non-empty and a multiple of 4 KiB")

    installer_data = json.loads(INSTALLER_DATA.read_text())
    partitions = installer_data["os_list"][0]["partitions"]
    efi = next((part for part in partitions if part.get("source") == "esp"), None)
    root = next((part for part in partitions if part.get("image") == "root.img"), None)
    if efi is None or root is None:
        raise ValueError("installer metadata must define esp and root.img package inputs")
    if image_size > int(root["size"].removesuffix("B")):
        raise ValueError("root image is larger than the minimum root partition")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nixos-gravity-package-") as tmp:
        esp = Path(tmp) / "esp"
        assemble(nixos_esp, gravity_stage2_zip, esp)
        created_output = False
        try:
            with output.open("xb") as stream:
                created_output = True
                with zipfile.ZipFile(
                    stream,
                    mode="w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=1,
                    allowZip64=True,
                ) as package:
                    for path in sorted(esp.rglob("*")):
                        if path.is_file():
                            package.write(path, f"esp/{path.relative_to(esp).as_posix()}")
                    package.write(root_image, "root.img")
                    package.write(BOOT_SOURCES, "BOOT-SOURCES.json")

            with zipfile.ZipFile(output) as package:
                bad_member = package.testzip()
                if bad_member is not None:
                    raise ValueError(f"installer package ZIP failed CRC validation: {bad_member}")
                names = set(package.namelist())
                required = {
                    "root.img",
                    "BOOT-SOURCES.json",
                    "esp/EFI/BOOT/BOOTAA64.EFI",
                    "esp/EFI/Linux/nixos-gravity.efi",
                    "esp/m1n1/boot.bin",
                }
                missing = required - names
                if missing:
                    raise ValueError(f"installer package lacks required members: {sorted(missing)}")
                if package.getinfo("root.img").file_size != image_size:
                    raise ValueError("root image size changed while packaging")
        except Exception:
            if created_output:
                output.unlink(missing_ok=True)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nixos_esp", type=Path)
    parser.add_argument("gravity_stage2_zip", type=Path)
    parser.add_argument("root_image", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    make_package(args.nixos_esp, args.gravity_stage2_zip, args.root_image, args.output)
    print(f"created Gravity installer package at {args.output}")


if __name__ == "__main__":
    main()
