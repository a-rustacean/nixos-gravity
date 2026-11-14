#!/usr/bin/env python3
"""Set one mounted APFS volume's VolBootable flag as a privileged helper."""

import argparse
import ctypes
import json
import os
import plistlib
import re
import subprocess
import sys


APFSIOC_VOL_BOOTABLE = 0xC0044A57
APFS_CONTENT = "41504653-0000-11AA-AA11-00306543ECAC"


def validate_model():
    model = subprocess.check_output(
        ["/usr/sbin/sysctl", "-n", "hw.model"], text=True
    ).strip()
    with open(os.path.join(os.path.dirname(__file__), "installer_data.json")) as stream:
        data = json.load(stream)
    supported = {
        product_type
        for entry in data.get("os_list", [])
        for product_type in entry.get("models", [])
    }
    if not supported or model not in supported:
        raise ValueError(f"model {model!r} is not supported by this Gravity installer kit")
    return model


def disk_info(target):
    raw = subprocess.check_output(["/usr/sbin/diskutil", "info", "-plist", target])
    return plistlib.loads(raw)


def validate_target(path):
    volumes_root = os.path.realpath("/Volumes")
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ValueError("target must be a canonical absolute mount path")

    canonical = os.path.realpath(path)
    if os.path.dirname(canonical) != volumes_root:
        raise ValueError("target must be a direct mounted volume under /Volumes")

    info = disk_info(canonical)
    if info.get("MountPoint") != canonical:
        raise ValueError("target is not mounted at the requested path")
    if info.get("Content", "").upper() != APFS_CONTENT:
        raise ValueError("target is not an APFS volume")
    if not re.fullmatch(r"disk\d+s\d+", info.get("DeviceIdentifier", "")):
        raise ValueError("target does not resolve to a physical disk volume")
    if not re.fullmatch(
        r"[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}",
        info.get("VolumeUUID", ""),
    ):
        raise ValueError("target has no valid APFS volume UUID")
    if not info.get("APFSContainerReference"):
        raise ValueError("target has no APFS container")
    return info


def set_volbootable(path, value):
    library = ctypes.CDLL("libSystem.B.dylib", use_errno=True)
    fsctl = library.fsctl
    fsctl.restype = ctypes.c_int
    fsctl.argtypes = (
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
    )
    command = ctypes.c_int(value)
    result = fsctl(path.encode(), APFSIOC_VOL_BOOTABLE, ctypes.byref(command), 0)
    if result == -1:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mount_path")
    parser.add_argument("value", type=int, choices=(-1, 1))
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        parser.error("this helper only runs on macOS")
    if os.geteuid() != 0:
        parser.error("this helper must be invoked through sudo")

    try:
        validate_model()
    except (OSError, ValueError) as error:
        parser.error(str(error))

    info = validate_target(args.mount_path)
    set_volbootable(args.mount_path, args.value)
    print(
        f"Set VolBootable={args.value} on {info['DeviceIdentifier']} "
        f"({info['VolumeName']}, {info['VolumeUUID']})."
    )


if __name__ == "__main__":
    main()
