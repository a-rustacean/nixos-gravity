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
        (source / "Frameworks/Python.framework/Versions/3.13/bin/python3.13").write_bytes(
            b"synthetic python runtime binary"
        )
        (source / "Frameworks/Python.framework/Versions/Current").symlink_to("3.13")
        archive_path = root / "gravity-runtime.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(source, arcname=".")
        return archive_path

    def make_package(self, root: Path) -> Path:
        package_path = root / "nixos-gravity-j773g.zip"
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
                make_release_kit.make_release_kit(runtime_archive, package, "test-1", output)

            kit_archive = output / "installer-test-1.tar.gz"
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
                self.assertTrue(regular_files <= checksums.keys())
                self.assertIn(
                    "gravity-installer/Frameworks/Python.framework/Versions/3.13/bin/python3.13",
                    checksums,
                )
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
                self.assertEqual((output / "latest").read_text(), "test-1\n")

            self.assertTrue((output / "installer-test-1.tar.gz.sha256").is_file())
            self.assertTrue((output / "nixos-gravity-j773g.zip.sha256").is_file())

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
                    make_release_kit.make_release_kit(runtime_archive, package, "test-1", output)

            self.assertEqual(latest.read_text(), "previous\n")
            self.assertEqual(sorted(path.name for path in output.iterdir()), ["latest"])


if __name__ == "__main__":
    unittest.main()
