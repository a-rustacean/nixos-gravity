#!/usr/bin/env python3
"""Set one NixOS Preboot admin plist's system-immutable flag as root."""

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys


APFS_CONTENT = "41504653-0000-11AA-AA11-00306543ECAC"
APFS_PARTITION_CONTENT = "Apple_APFS"
PREBOOT_MOUNT = "/Volumes/Preboot"
SYSTEM_NAME = "NixOS Gravity"
DATA_NAME = "NixOS Gravity - Data"
ADMIN_PLIST = "AdminUserRecoveryInfo.plist"
UUID_PATTERN = re.compile(
    r"[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}"
)


def disk_info(target):
    raw = subprocess.check_output(
        ["/usr/sbin/diskutil", "info", "-plist", target]
    )
    return plistlib.loads(raw)


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


def apfs_containers():
    raw = subprocess.check_output(
        ["/usr/sbin/diskutil", "apfs", "list", "-plist"]
    )
    return plistlib.loads(raw).get("Containers", [])


def unique_container(containers, container_ref):
    matches = [item for item in containers if item.get("ContainerReference") == container_ref]
    if len(matches) != 1:
        raise ValueError("could not uniquely identify the target APFS container")
    return matches[0]


def validate_target(path):
    if not os.path.isabs(path) or os.path.normpath(path) != path:
        raise ValueError("target must be a canonical absolute path")
    if os.path.realpath(path) != path or os.path.islink(path):
        raise ValueError("target path must not contain symlinks")
    if not os.path.isfile(path):
        raise ValueError("target must be an existing regular file")

    prefix = PREBOOT_MOUNT + os.sep
    if not path.startswith(prefix):
        raise ValueError("target must be inside the NixOS Preboot mount")
    components = path[len(prefix):].split(os.sep)
    if (
        len(components) != 4
        or components[1:] != ["var", "db", ADMIN_PLIST]
        or not UUID_PATTERN.fullmatch(components[0])
    ):
        raise ValueError("target must be <NixOS-volume-group>/var/db/AdminUserRecoveryInfo.plist")
    group_uuid = components[0].upper()

    preboot = disk_info(PREBOOT_MOUNT)
    if preboot.get("MountPoint") != PREBOOT_MOUNT:
        raise ValueError("Preboot is not mounted at the expected path")
    if preboot.get("VolumeName") != "Preboot":
        raise ValueError("target mount is not the Preboot volume")
    if preboot.get("Content", "").upper() != APFS_CONTENT:
        raise ValueError("Preboot target is not APFS")

    container_ref = preboot.get("APFSContainerReference")
    if not container_ref:
        raise ValueError("Preboot has no APFS container")
    containers = apfs_containers()
    container = unique_container(containers, container_ref)
    stores = [
        item.get("DeviceIdentifier") for item in container.get("PhysicalStores", [])
    ]
    if len(stores) != 1 or not re.fullmatch(r"disk0s[1-9][0-9]*", stores[0] or ""):
        raise ValueError("NixOS Preboot must be on one dedicated disk0 APFS partition")

    booted = disk_info("/")
    if booted.get("MountPoint") != "/" or booted.get("Content", "").upper() != APFS_CONTENT:
        raise ValueError("could not verify the currently booted macOS APFS volume")
    boot_container_ref = booted.get("APFSContainerReference")
    if not boot_container_ref or boot_container_ref == container_ref:
        raise ValueError("refusing to modify the currently booted macOS container")
    boot_container = unique_container(containers, boot_container_ref)
    boot_stores = {
        item.get("APFSPhysicalStore") for item in booted.get("APFSPhysicalStores", [])
    }
    boot_container_stores = {
        item.get("DeviceIdentifier") for item in boot_container.get("PhysicalStores", [])
    }
    if not boot_stores or not boot_stores.issubset(boot_container_stores):
        raise ValueError("could not match booted macOS to its APFS physical store")

    protected_stores = {
        item.get("DeviceIdentifier")
        for other in containers
        if other.get("ContainerReference") != container_ref
        for item in other.get("PhysicalStores", [])
    }
    protected_stores.update(boot_stores)
    if stores[0] in protected_stores:
        raise ValueError("NixOS Preboot physical store overlaps another APFS container")

    whole_disk = disk_info("disk0")
    if (
        whole_disk.get("DeviceIdentifier") != "disk0"
        or not whole_disk.get("WholeDisk")
        or not whole_disk.get("Internal")
    ):
        raise ValueError("disk0 is not the expected internal physical disk")
    physical_store = disk_info(stores[0])
    if (
        physical_store.get("DeviceIdentifier") != stores[0]
        or physical_store.get("ParentWholeDisk") != "disk0"
        or not physical_store.get("PartitionMapPartition")
        or physical_store.get("Content") not in (APFS_PARTITION_CONTENT, APFS_CONTENT)
        or physical_store.get("APFSContainerReference") != container_ref
    ):
        raise ValueError("NixOS Preboot is not on its own APFS partition on disk0")

    volumes = container.get("Volumes", [])
    preboot_volumes = [
        volume for volume in volumes
        if "Preboot" in volume.get("Roles", [])
        and volume.get("DeviceIdentifier") == preboot.get("DeviceIdentifier")
    ]
    data_volumes = [
        volume for volume in volumes
        if "Data" in volume.get("Roles", [])
        and volume.get("APFSVolumeUUID", "").upper() == group_uuid
        and volume.get("Name") == DATA_NAME
    ]
    system_volumes = [
        volume for volume in volumes
        if "System" in volume.get("Roles", [])
        and volume.get("Name") == SYSTEM_NAME
    ]
    if len(preboot_volumes) != 1 or len(data_volumes) != 1 or len(system_volumes) != 1:
        raise ValueError("container is not the expected NixOS Gravity volume group")

    system_info = disk_info("/Volumes/" + system_volumes[0]["Name"])
    if system_info.get("APFSContainerReference") != container_ref:
        raise ValueError("NixOS system volume is outside the Preboot container")
    if system_info.get("APFSVolumeGroupID", "").upper() != group_uuid:
        raise ValueError("target path does not match the NixOS system volume group")

    return {
        "container": container_ref,
        "group_uuid": group_uuid,
        "preboot_device": preboot.get("DeviceIdentifier"),
        "physical_store": stores[0],
        "booted_container": boot_container_ref,
    }


def set_flags(path, flag):
    if flag not in ("schg", "noschg"):
        raise ValueError("only the system-immutable flag may be changed")
    subprocess.run(["/usr/bin/chflags", flag, path], check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("flag", choices=("schg", "noschg"))
    args = parser.parse_args(argv)

    if sys.platform != "darwin":
        parser.error("this helper only runs on macOS")
    if os.geteuid() != 0:
        parser.error("this helper must be invoked through sudo")

    try:
        validate_model()
    except (OSError, ValueError) as error:
        parser.error(str(error))

    target = validate_target(args.path)
    set_flags(args.path, args.flag)
    print(
        f"Set chflags {args.flag} on {target['preboot_device']} "
        f"for NixOS volume group {target['group_uuid']} on {target['physical_store']}."
    )


if __name__ == "__main__":
    main()
