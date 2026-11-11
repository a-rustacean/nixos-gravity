#!/usr/bin/env python3
import ctypes
import errno
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fsctl_bootable_helper
from patch_gravity_volbootable import (
    HELPER_NAME,
    NEW_FUNCTION,
    OLD_FUNCTION,
    OLD_IMPORT,
    patch_runtime,
    patch_source,
)


UTIL_FIXTURE = OLD_IMPORT + "from ctypes import *\n\n" + OLD_FUNCTION
VALID_INFO = {
    "Content": fsctl_bootable_helper.APFS_CONTENT,
    "DeviceIdentifier": "disk2s2",
    "MountPoint": "/Volumes/NixOS",
    "VolumeName": "NixOS",
    "VolumeUUID": "34182443-8984-477B-A8A7-DE02A30DCA9C",
    "APFSContainerReference": "disk2",
}


class GravityVolBootablePatchTest(unittest.TestCase):
    def test_patch_adds_narrow_elevated_fallback_and_is_idempotent(self):
        patched = patch_source(UTIL_FIXTURE)
        self.assertIn("errno.EPERM", patched)
        self.assertIn("/usr/bin/sudo", patched)
        self.assertIn("fsctl_bootable_helper.py", patched)
        self.assertIn("expected = 1 if cmd == 1 else -1", patched)
        self.assertEqual(patch_source(patched), patched)

    def test_patch_rejects_unknown_or_partial_upstream_layout(self):
        with self.assertRaisesRegex(ValueError, "unexpected Gravity"):
            patch_source(UTIL_FIXTURE.replace("lzma", "lzma ", 1))
        with self.assertRaisesRegex(ValueError, "partial VolBootable"):
            patch_source("fsctl_bootable_helper.py\n" + OLD_IMPORT)

    def test_runtime_installs_helper_and_refuses_to_replace_unknown_helper(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            (runtime / "util.py").write_text(UTIL_FIXTURE)
            patch_runtime(runtime)
            self.assertTrue((runtime / HELPER_NAME).is_file())
            self.assertIn("fsctl_bootable_helper.py", (runtime / "util.py").read_text())
            patch_runtime(runtime)
            (runtime / HELPER_NAME).write_text("not our helper\n")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                patch_runtime(runtime)

    def _patched_fsctl_namespace(self, denied_errno=errno.EPERM, query_fails=False):
        state = {"flag": -1, "errno": denied_errno}

        class FakeFsctl:
            def __call__(self, path, request, command, options):
                value = command._obj.value
                if value == 0:
                    if query_fails:
                        return -1
                    command._obj.value = state["flag"]
                    return 0
                state["errno"] = denied_errno
                return -1

        fake_fsctl = FakeFsctl()

        def run(arguments, check):
            self.assertEqual(arguments[0:2], ["/usr/bin/sudo", "/usr/bin/env"])
            state["flag"] = int(arguments[-1])

        subprocess_mock = mock.Mock()
        subprocess_mock.run.side_effect = run
        namespace = {
            "CDLL": lambda *args, **kwargs: type(
                "Library", (), {"fsctl": fake_fsctl}
            )(),
            "c_int": ctypes.c_int,
            "c_char_p": ctypes.c_char_p,
            "c_ulong": ctypes.c_ulong,
            "POINTER": ctypes.POINTER,
            "c_uint": ctypes.c_uint,
            "byref": ctypes.byref,
            "get_errno": lambda: state["errno"],
            "errno": errno,
            "os": os,
            "sys": sys,
            "subprocess": subprocess_mock,
            "logging": logging,
            "__file__": "/tmp/gravity-runtime/util.py",
        }
        exec(compile(NEW_FUNCTION, "<patched-gravity-util>", "exec"), namespace)
        return namespace, state

    def test_eperm_mutation_uses_sudo_helper_then_verifies_flag(self):
        namespace, state = self._patched_fsctl_namespace()
        self.assertEqual(namespace["fsctl_apfs_bootable"]("/Volumes/NixOS", 1), 1)
        self.assertEqual(state["flag"], 1)
        namespace["subprocess"].run.assert_called_once()
        arguments = namespace["subprocess"].run.call_args.args[0]
        self.assertEqual(arguments[-2:], ["/Volumes/NixOS", "1"])
        self.assertTrue(arguments[-3].endswith("fsctl_bootable_helper.py"))

    def test_query_and_non_permission_errors_never_use_sudo(self):
        namespace, _ = self._patched_fsctl_namespace(query_fails=True)
        with self.assertRaisesRegex(Exception, "errno: 1"):
            namespace["fsctl_apfs_bootable"]("/Volumes/NixOS", 0)
        namespace["subprocess"].run.assert_not_called()

        namespace, _ = self._patched_fsctl_namespace(denied_errno=errno.EIO)
        with self.assertRaisesRegex(Exception, f"errno: {errno.EIO}"):
            namespace["fsctl_apfs_bootable"]("/Volumes/NixOS", 1)
        namespace["subprocess"].run.assert_not_called()

    def test_privileged_helper_accepts_only_direct_mounted_apfs_volume(self):
        with mock.patch.object(fsctl_bootable_helper, "disk_info", return_value=VALID_INFO):
            self.assertEqual(
                fsctl_bootable_helper.validate_target("/Volumes/NixOS"), VALID_INFO
            )
            for path in ("/", "/Volumes/NixOS/child", "relative/path"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    fsctl_bootable_helper.validate_target(path)

    def test_privileged_helper_rejects_wrong_mount_or_non_apfs_volume(self):
        for changes in (
            {"MountPoint": "/Volumes/Other"},
            {"Content": "Apple_HFS"},
            {"DeviceIdentifier": "disk2"},
            {"VolumeUUID": "not-a-uuid"},
            {"APFSContainerReference": ""},
        ):
            info = {**VALID_INFO, **changes}
            with mock.patch.object(fsctl_bootable_helper, "disk_info", return_value=info):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    fsctl_bootable_helper.validate_target("/Volumes/NixOS")


if __name__ == "__main__":
    unittest.main()
