#!/usr/bin/env python3
"""Check the pinned Gravity boot sources against the build workflow."""

import json
import re
from pathlib import Path


root = Path(__file__).resolve().parent.parent
sources = json.loads((root / "installer/boot-sources.json").read_text())
workflow = (root / ".github/workflows/gravity-boot.yml").read_text()

for key, env_name in (
    ("gravity_installer", "GRAVITY_INSTALLER_REF"),
    ("gravity_bootloader", "GRAVITY_BOOTLOADER_REF"),
    ("gravity_linux", "GRAVITY_LINUX_REF"),
    ("gravity_u_boot", "GRAVITY_UBOOT_REF"),
):
    revision = sources[key]["revision"]
    assert re.fullmatch(r"[0-9a-f]{40}", revision), f"{key} is not pinned to a full commit"
    assert f"{env_name}: {revision}" in workflow, f"{key} pin differs from workflow"

print("Gravity m1n1, Linux DTB, and U-Boot sources are pinned consistently")
