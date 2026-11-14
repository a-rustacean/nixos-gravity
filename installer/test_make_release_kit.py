#!/usr/bin/env python3
import hashlib
import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_release_kit
from patch_gravity_volbootable import OLD_FUNCTION, OLD_IMPORT
from patch_gravity_preboot_chflags import OLD_METHOD


URLCACHE_FIXTURE = '''from util import *

class URLCache:
    def get_size(self):
        con.request("HEAD", self.url.path, headers={"Connection":" keep-alive"})

    def get_partial(self, off, size, bypass_cache=False):
        path = self.url.path
        if bypass_cache:
            path += f"?{random.random()}"
        con.request("GET", path)
'''
VOLBOOTABLE_FIXTURE = OLD_IMPORT + "from ctypes import *\n\n" + OLD_FUNCTION
STUB_FIXTURE = "import os, os.path, sys, subprocess, logging\n\nclass StubInstaller:\n" + OLD_METHOD


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MakeReleaseKitTest(unittest.TestCase):
    def make_runtime_archive(self, root: Path) -> Path:
        source = root / "runtime"
        (source / "Frameworks/Python.framework/Versions/3.13/bin").mkdir(parents=True)
        (source / "bin").mkdir()
        install = source / "install.sh"
        install.write_text("#!/bin/sh\nexit 0\n")
        install.chmod(0o755)
        (source / "version.tag").write_text("test-version\n")
        (source / "urlcache.py").write_text(URLCACHE_FIXTURE)
        (source / "util.py").write_text(VOLBOOTABLE_FIXTURE)
        (source / "stub.py").write_text(STUB_FIXTURE)
        (source / "Frameworks/Python.framework/Versions/3.13/._python3.13").write_bytes(
            b"AppleDouble resource-fork fixture"
        )
        (source / "Frameworks/Python.framework/Versions/3.13/bin/python3.13").write_bytes(
            b"synthetic python runtime binary"
        )
        (source / "Frameworks/Python.framework/Versions/Current").symlink_to("3.13")
        archive_path = root / "gravity-runtime.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(source, arcname=".")
        return archive_path

    def make_package(self, root: Path) -> Path:
        package_path = root / "nixos-gravity-mac-mini-m4.zip"
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_STORED) as package:
            for name in make_release_kit.REQUIRED_PACKAGE_MEMBERS:
                package.writestr(name, b"R" * 4096 if name == "root.img" else b"fixture")
        return package_path

    def with_runtime_pins(self, runtime_archive: Path):
        source = dict(make_release_kit.RUNTIME_SOURCE)
        source["sha256"] = digest(runtime_archive)
        return mock.patch.object(make_release_kit, "RUNTIME_SOURCE", source)

    def test_release_kit_checksums_every_regular_bundled_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_archive = self.make_runtime_archive(root)
            package = self.make_package(root)
            output = root / "assets"

            with self.with_runtime_pins(runtime_archive):
                make_release_kit.make_release_kit(
                    runtime_archive, package, "mac-mini-m4", "test-1", output
                )

            kit_archive = output / "installer-test-1-mac-mini-m4.tar.gz"
            with tarfile.open(kit_archive, "r:gz") as archive:
                manifest = archive.extractfile("SHA256SUMS").read().decode()
                checksums = {
                    line.partition("  ")[2]: line.partition("  ")[0]
                    for line in manifest.splitlines()
                }
                regular_files = {
                    member.name
                    for member in archive.getmembers()
                    if member.isfile() and member.name != "SHA256SUMS"
                }
                checksum_files = {
                    name for name in regular_files
                    if not make_release_kit.is_appledouble_path(name)
                }
                self.assertTrue(checksum_files <= checksums.keys())
                appledouble = (
                    "gravity-installer/Frameworks/Python.framework/Versions/3.13/._python3.13"
                )
                self.assertIn(appledouble, regular_files)
                self.assertNotIn(appledouble, checksums)
                self.assertIn(
                    "gravity-installer/Frameworks/Python.framework/Versions/3.13/bin/python3.13",
                    checksums,
                )
                self.assertEqual(
                    archive.extractfile("SUPPORTED-MODELS").read().decode(),
                    "Mac16,10\n",
                )
                installer_data = json.load(
                    archive.extractfile("gravity-installer/installer_data.json")
                )
                self.assertEqual(installer_data["os_list"][0]["kit"], "mac-mini-m4")
                self.assertEqual(installer_data["os_list"][0]["models"], ["Mac16,10"])
                runtime_source = archive.extractfile("gravity-installer/urlcache.py").read().decode()
                self.assertIn("_request_path(self.url)", runtime_source)
                util_source = archive.extractfile("gravity-installer/util.py").read().decode()
                self.assertIn("errno.EPERM", util_source)
                self.assertIn("fsctl_bootable_helper.py", util_source)
                helper = archive.extractfile(
                    "gravity-installer/fsctl_bootable_helper.py"
                ).read().decode()
                self.assertIn("APFSIOC_VOL_BOOTABLE", helper)
                self.assertIn("def validate_target(path):", helper)
                stub = archive.extractfile("gravity-installer/stub.py").read().decode()
                self.assertIn("preboot_chflags_helper.py", stub)
                preboot_helper = archive.extractfile(
                    "gravity-installer/preboot_chflags_helper.py"
                ).read().decode()
                self.assertIn("def apfs_containers():", preboot_helper)
                self.assertIn("protected_stores", preboot_helper)
                self.assertIn('ParentWholeDisk") != "disk0"', preboot_helper)
                self.assertEqual((output / "latest").read_text(), "test-1\n")

            # macOS tar consumes AppleDouble sidecars into resource forks instead of
            # leaving them as files. The install-time SHA256SUMS check must still pass.
            with tempfile.TemporaryDirectory() as extracted:
                with tarfile.open(kit_archive, "r:gz") as archive:
                    archive.extractall(extracted, filter="data")
                appledouble_path = Path(extracted) / appledouble
                appledouble_path.unlink()
                for line in (Path(extracted) / "SHA256SUMS").read_text().splitlines():
                    expected, _, name = line.partition("  ")
                    self.assertEqual(digest(Path(extracted) / name), expected, name)

            self.assertTrue((output / "installer-test-1-mac-mini-m4.tar.gz.sha256").is_file())
            self.assertTrue((output / "nixos-gravity-mac-mini-m4.zip.sha256").is_file())
            self.assertEqual((output / "supported-models.txt").read_text(), "Mac16,10 mac-mini-m4\n")

    def test_existing_asset_is_not_overwritten_or_partially_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_archive = self.make_runtime_archive(root)
            package = self.make_package(root)
            output = root / "assets"
            output.mkdir()
            latest = output / "latest"
            latest.write_text("previous\n")

            with self.with_runtime_pins(runtime_archive):
                with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                    make_release_kit.make_release_kit(
                        runtime_archive, package, "mac-mini-m4", "test-1", output
                    )

            self.assertEqual(latest.read_text(), "previous\n")
            self.assertEqual(sorted(path.name for path in output.iterdir()), ["latest"])


if __name__ == "__main__":
    unittest.main()
