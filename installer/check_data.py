#!/usr/bin/env python3
"""Check that the Gravity installer metadata matches the NixOS image layout."""

import json
from pathlib import Path


root = Path(__file__).resolve().parent.parent
data = json.loads((Path(__file__).with_name("installer_data.json")).read_text())
assert len(data["os_list"]) == 1, "expected exactly one installable OS"
os_entry = data["os_list"][0]
assert os_entry["default_os_name"] == "NixOS Gravity"
assert os_entry["boot_object"] == "m1n1.bin"
assert os_entry["next_object"] == "m1n1/boot.bin"
assert os_entry["package"] == "nixos-gravity-j773g.zip"
assert os_entry["supported_fw"], "must pin the tested Gravity firmware version"

partitions = os_entry["partitions"]
assert [part["name"] for part in partitions] == ["EFI", "Root"]
efi, root_partition = partitions
assert efi["type"] == "EFI" and efi["format"] == "fat"
assert efi["size"] == "524288000B"
assert efi["source"] == "esp"
assert efi["copy_firmware"] is True
assert efi["copy_installer_data"] is True
assert root_partition["type"] == "Linux"
assert root_partition["image"] == "root.img"
assert root_partition["expand"] is True
assert int(root_partition["size"].removesuffix("B")) == 32 * 1024**3

configuration = (root / "configuration.nix").read_text()
assert 'device = "/dev/disk/by-uuid/7a773000-0000-4000-8000-000000000001";' in configuration
assert 'device = "/dev/disk/by-partlabel/EFI - NixOS Gravity";' in configuration
print("Gravity installer metadata matches the J773g root and ESP layout")
