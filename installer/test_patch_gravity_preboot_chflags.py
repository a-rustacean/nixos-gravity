#!/usr/bin/env python3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preboot_chflags_helper
from patch_gravity_preboot_chflags import (
    HELPER_NAME,
    NEW_METHOD,
    OLD_METHOD,
    patch_runtime,
    patch_source,
)


STUB_FIXTURE = """import os, sys, subprocess, logging

class StubInstaller:
""" + OLD_METHOD
GROUP_UUID = "C00CC011-DED9-4F9F-BBA6-FC0118A24C14"
TARGET = f"/Volumes/Preboot/{GROUP_UUID}/var/db/AdminUserRecoveryInfo.plist"
PREBOOT_INFO = {
    "MountPoint": "/Volumes/Preboot",
    "VolumeName": "Preboot",
    "Content": preboot_chflags_helper.APFS_CONTENT,
    "DeviceIdentifier": "disk4s3",
    "APFSContainerReference": "disk4",
}
SYSTEM_INFO = {
    "MountPoint": "/Volumes/NixOS Gravity",
    "VolumeName": "NixOS Gravity",
    "APFSContainerReference": "disk4",
    "APFSVolumeGroupID": GROUP_UUID,
}
TARGET_CONTAINER = {
    "ContainerReference": "disk4",
    "PhysicalStores": [{"DeviceIdentifier": "disk0s5"}],
    "Volumes": [
        {
            "DeviceIdentifier": "disk4s1",
            "APFSVolumeUUID": GROUP_UUID,
            "Name": "NixOS Gravity - Data",
            "Roles": ["Data"],
        },
        {
            "DeviceIdentifier": "disk4s2",
            "APFSVolumeUUID": "4C31B9CD-F104-4962-A5B6-8B2A618C354D",
            "Name": "NixOS Gravity",
            "Roles": ["System"],
        },
        {
            "DeviceIdentifier": "disk4s3",
            "APFSVolumeUUID": "9B27B1D1-293B-42B6-98C9-20E2506340C1",
            "Name": "Preboot",
            "Roles": ["Preboot"],
        },
        {
            "DeviceIdentifier": "disk4s4",
            "APFSVolumeUUID": "3E7E643C-66C8-4471-BF49-7F28651051C3",
            "Name": "Recovery",
            "Roles": ["Recovery"],
        },
    ],
}
MACOS_CONTAINER = {
    "ContainerReference": "disk3",
    "PhysicalStores": [{"DeviceIdentifier": "disk0s2"}],
    "Volumes": [
        {"DeviceIdentifier": "disk3s1", "Name": "Macintosh HD - Data", "Roles": ["Data"]},
        {"DeviceIdentifier": "disk3s5", "Name": "Macintosh HD", "Roles": ["System"]},
        {"DeviceIdentifier": "disk3s2", "Name": "Preboot", "Roles": ["Preboot"]},
        {"DeviceIdentifier": "disk3s3", "Name": "Recovery", "Roles": ["Recovery"]},
    ],
}
APPLE_RECOVERY_CONTAINER = {
    "ContainerReference": "disk2",
    "PhysicalStores": [{"DeviceIdentifier": "disk0s3"}],
    "Volumes": [
        {"DeviceIdentifier": "disk2s1", "Name": "Recovery", "Roles": ["Recovery"]},
        {"DeviceIdentifier": "disk2s2", "Name": "Update", "Roles": ["Update"]},
    ],
}
ISC_CONTAINER = {
    "ContainerReference": "disk1",
    "PhysicalStores": [{"DeviceIdentifier": "disk0s1"}],
    "Volumes": [
        {"DeviceIdentifier": "disk1s1", "Name": "iSCPreboot", "Roles": ["iSCPreboot"]}
    ],
}
APFS_CONTAINERS = [
    TARGET_CONTAINER,
    MACOS_CONTAINER,
    APPLE_RECOVERY_CONTAINER,
    ISC_CONTAINER,
]
BOOT_INFO = {
    "MountPoint": "/",
    "Content": preboot_chflags_helper.APFS_CONTENT,
    "APFSContainerReference": "disk3",
    "APFSPhysicalStores": [{"APFSPhysicalStore": "disk0s2"}],
}
DISK0_INFO = {
    "DeviceIdentifier": "disk0",
    "WholeDisk": True,
    "Internal": True,
}
TARGET_STORE_INFO = {
    "DeviceIdentifier": "disk0s5",
    "ParentWholeDisk": "disk0",
    "PartitionMapPartition": True,
    "Content": "Apple_APFS",
    "APFSContainerReference": "disk4",
}


def valid_disk_info(path):
    return {
        "/Volumes/Preboot": PREBOOT_INFO,
        "/Volumes/NixOS Gravity": SYSTEM_INFO,
        "/": BOOT_INFO,
        "disk0": DISK0_INFO,
        "disk0s5": TARGET_STORE_INFO,
    }[path]


class GravityPrebootChflagsPatchTest(unittest.TestCase):
    def test_privileged_helper_model_allowlist_comes_from_installer_metadata(self):
        with mock.patch.object(
            preboot_chflags_helper.subprocess,
            "check_output",
            return_value="Mac16,10\n",
        ):
            self.assertEqual(preboot_chflags_helper.validate_model(), "Mac16,10")
        with mock.patch.object(
            preboot_chflags_helper.subprocess,
            "check_output",
            return_value="Mac16,11\n",
        ):
            with self.assertRaisesRegex(ValueError, "not supported"):
                preboot_chflags_helper.validate_model()

    def test_patch_elevates_only_system_immutable_flag_operations(self):
        patched = patch_source(STUB_FIXTURE)
        self.assertIn("subprocess.CalledProcessError", patched)
        self.assertIn('flags not in ("schg", "noschg")', patched)
        self.assertIn("/usr/bin/sudo", patched)
        self.assertIn("preboot_chflags_helper.py", patched)
        self.assertEqual(patch_source(patched), patched)

    def test_patch_rejects_unknown_or_partial_upstream_method(self):
        with self.assertRaisesRegex(ValueError, "unexpected Gravity"):
            patch_source(STUB_FIXTURE.replace('"chflags"', '"chflags-x"', 1))
        with self.assertRaisesRegex(ValueError, "partial Preboot"):
            patch_source(HELPER_NAME + "\n" + OLD_METHOD)

    def test_runtime_adds_helper_and_patches_stub(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            (runtime / "stub.py").write_text(STUB_FIXTURE)
            patch_runtime(runtime)
            self.assertTrue((runtime / HELPER_NAME).is_file())
            self.assertIn(HELPER_NAME, (runtime / "stub.py").read_text())
            patch_runtime(runtime)
            (runtime / HELPER_NAME).write_text("unexpected helper")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                patch_runtime(runtime)

    def test_preboot_helper_accepts_dedicated_stub_between_macos_and_recovery(self):
        with (
            mock.patch.object(preboot_chflags_helper, "disk_info", side_effect=valid_disk_info),
            mock.patch.object(
                preboot_chflags_helper,
                "apfs_containers",
                return_value=APFS_CONTAINERS,
            ),
            mock.patch.object(preboot_chflags_helper.os.path, "realpath", side_effect=lambda p: p),
            mock.patch.object(preboot_chflags_helper.os.path, "isfile", return_value=True),
            mock.patch.object(preboot_chflags_helper.os.path, "islink", return_value=False),
        ):
            target = preboot_chflags_helper.validate_target(TARGET)
        self.assertEqual(target["group_uuid"], GROUP_UUID)
        self.assertEqual(target["physical_store"], "disk0s5")
        self.assertEqual(target["booted_container"], "disk3")

    def test_preboot_helper_rejects_wrong_paths_containers_or_groups(self):
        bad_paths = (
            "/Volumes/Preboot/other/var/db/AdminUserRecoveryInfo.plist",
            f"/Volumes/Preboot/{GROUP_UUID}/var/db/other.plist",
            f"/Volumes/Preboot/{GROUP_UUID}/var/db/../AdminUserRecoveryInfo.plist",
            f"/Volumes/Other/{GROUP_UUID}/var/db/AdminUserRecoveryInfo.plist",
        )
        for path in bad_paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                preboot_chflags_helper.validate_target(path)

        for changes in (
            {"MountPoint": "/Volumes/Other"},
            {"VolumeName": "Recovery"},
            {"Content": "Apple_HFS"},
            {"APFSContainerReference": "disk3"},
        ):
            changed_preboot = {**PREBOOT_INFO, **changes}
            with (
                self.subTest(changes=changes),
                mock.patch.object(
                    preboot_chflags_helper, "disk_info",
                    side_effect=lambda path: {
                        **{
                            "/Volumes/NixOS Gravity": SYSTEM_INFO,
                            "/": BOOT_INFO,
                            "disk0": DISK0_INFO,
                            "disk0s5": TARGET_STORE_INFO,
                        },
                        "/Volumes/Preboot": changed_preboot,
                    }[path],
                ),
                mock.patch.object(
                    preboot_chflags_helper, "apfs_containers",
                    return_value=APFS_CONTAINERS,
                ),
                mock.patch.object(preboot_chflags_helper.os.path, "realpath", side_effect=lambda p: p),
                mock.patch.object(preboot_chflags_helper.os.path, "isfile", return_value=True),
                mock.patch.object(preboot_chflags_helper.os.path, "islink", return_value=False),
                self.assertRaises(ValueError),
            ):
                preboot_chflags_helper.validate_target(TARGET)

    def test_preboot_helper_rejects_macos_recovery_and_isc_stores(self):
        for protected_store in ("disk0s1", "disk0s2", "disk0s3"):
            target_container = {
                **TARGET_CONTAINER,
                "PhysicalStores": [{"DeviceIdentifier": protected_store}],
            }
            containers = [target_container, *APFS_CONTAINERS[1:]]
            with (
                self.subTest(protected_store=protected_store),
                mock.patch.object(
                    preboot_chflags_helper, "disk_info", side_effect=valid_disk_info
                ),
                mock.patch.object(
                    preboot_chflags_helper, "apfs_containers", return_value=containers
                ),
                mock.patch.object(preboot_chflags_helper.os.path, "realpath", side_effect=lambda p: p),
                mock.patch.object(preboot_chflags_helper.os.path, "isfile", return_value=True),
                mock.patch.object(preboot_chflags_helper.os.path, "islink", return_value=False),
                self.assertRaisesRegex(ValueError, "overlaps another APFS container"),
            ):
                preboot_chflags_helper.validate_target(TARGET)

    def test_preboot_helper_rejects_non_disk0_or_non_apfs_partitions(self):
        invalid_stores = (
            [{"DeviceIdentifier": "disk1s5"}],
            [{"DeviceIdentifier": "disk0"}],
            [{"DeviceIdentifier": "disk0s5"}, {"DeviceIdentifier": "disk0s6"}],
        )
        for stores in invalid_stores:
            container = {**TARGET_CONTAINER, "PhysicalStores": stores}
            with (
                self.subTest(stores=stores),
                mock.patch.object(preboot_chflags_helper, "disk_info", side_effect=valid_disk_info),
                mock.patch.object(
                    preboot_chflags_helper,
                    "apfs_containers",
                    return_value=[container, *APFS_CONTAINERS[1:]],
                ),
                mock.patch.object(preboot_chflags_helper.os.path, "realpath", side_effect=lambda p: p),
                mock.patch.object(preboot_chflags_helper.os.path, "isfile", return_value=True),
                mock.patch.object(preboot_chflags_helper.os.path, "islink", return_value=False),
                self.assertRaises(ValueError),
            ):
                preboot_chflags_helper.validate_target(TARGET)

        for changes in (
            {"ParentWholeDisk": "disk1"},
            {"PartitionMapPartition": False},
            {"Content": "Apple_APFS_Recovery"},
            {"APFSContainerReference": "disk3"},
        ):
            with (
                self.subTest(store_changes=changes),
                mock.patch.object(
                    preboot_chflags_helper,
                    "disk_info",
                    side_effect=lambda path: {
                        **valid_disk_info(path),
                        **(changes if path == "disk0s5" else {}),
                    },
                ),
                mock.patch.object(
                    preboot_chflags_helper, "apfs_containers", return_value=APFS_CONTAINERS
                ),
                mock.patch.object(preboot_chflags_helper.os.path, "realpath", side_effect=lambda p: p),
                mock.patch.object(preboot_chflags_helper.os.path, "isfile", return_value=True),
                mock.patch.object(preboot_chflags_helper.os.path, "islink", return_value=False),
                self.assertRaisesRegex(ValueError, "own APFS partition"),
            ):
                preboot_chflags_helper.validate_target(TARGET)

    def test_preboot_helper_changes_only_schg_and_noschg(self):
        with mock.patch.object(preboot_chflags_helper.subprocess, "run") as run:
            preboot_chflags_helper.set_flags(TARGET, "schg")
            preboot_chflags_helper.set_flags(TARGET, "noschg")
        self.assertEqual(
            run.call_args_list,
            [
                mock.call(["/usr/bin/chflags", "schg", TARGET], check=True),
                mock.call(["/usr/bin/chflags", "noschg", TARGET], check=True),
            ],
        )
        with self.assertRaisesRegex(ValueError, "only the system-immutable"):
            preboot_chflags_helper.set_flags(TARGET, "uchg")

    def test_stub_falls_back_to_validated_helper_for_schg_only(self):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(
                    1, args, stderr=f"chflags: {TARGET}: Operation not permitted"
                )

        namespace = {
            "logging": __import__("logging"),
            "subprocess": mock.Mock(
                run=run, CalledProcessError=subprocess.CalledProcessError
            ),
            "os": __import__("os"),
            "sys": sys,
            "__file__": "/tmp/gravity-runtime/stub.py",
        }
        exec(compile(textwrap.dedent(NEW_METHOD), "<patched-gravity-stub>", "exec"), namespace)
        namespace["StubInstaller"] = type("StubInstaller", (), {})
        namespace["StubInstaller"].chflags = namespace["chflags"]
        namespace["StubInstaller"]().chflags("schg", TARGET)
        self.assertEqual(calls[0], ["chflags", "schg", TARGET])
        self.assertEqual(
            calls[1][-3:],
            ["/tmp/gravity-runtime/preboot_chflags_helper.py", TARGET, "schg"],
        )

    def test_stub_does_not_escalate_other_failed_flags(self):
        run = mock.Mock(
            side_effect=subprocess.CalledProcessError(
                1, ["chflags"], stderr="chflags: Operation not permitted"
            )
        )
        namespace = {
            "logging": __import__("logging"),
            "subprocess": mock.Mock(
                run=run, CalledProcessError=subprocess.CalledProcessError
            ),
            "os": __import__("os"),
            "sys": sys,
            "__file__": "/tmp/gravity-runtime/stub.py",
        }
        exec(compile(textwrap.dedent(NEW_METHOD), "<patched-gravity-stub>", "exec"), namespace)
        with self.assertRaises(subprocess.CalledProcessError):
            namespace["chflags"](None, "uchg", TARGET)
        run.assert_called_once()

    def test_stub_does_not_escalate_non_permission_chflags_failures(self):
        run = mock.Mock(
            side_effect=subprocess.CalledProcessError(
                1, ["chflags"], stderr="chflags: No such file or directory"
            )
        )
        namespace = {
            "logging": __import__("logging"),
            "subprocess": mock.Mock(
                run=run, CalledProcessError=subprocess.CalledProcessError
            ),
            "os": __import__("os"),
            "sys": sys,
            "__file__": "/tmp/gravity-runtime/stub.py",
        }
        exec(compile(textwrap.dedent(NEW_METHOD), "<patched-gravity-stub>", "exec"), namespace)
        with self.assertRaises(subprocess.CalledProcessError):
            namespace["chflags"](None, "schg", TARGET)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
