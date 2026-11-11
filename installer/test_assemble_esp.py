#!/usr/bin/env python3
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble_esp import REQUIRED_FILES, STAGE2_MEMBER, assemble
from make_installer_package import make_package


class AssembleEspTest(unittest.TestCase):
    def test_merges_boot_payload_without_overwriting_nixos_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            esp = root / "nixos-esp"
            for relative in REQUIRED_FILES:
                path = esp / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode())

            stage2 = root / "stage2.zip"
            with zipfile.ZipFile(stage2, "w") as archive:
                archive.writestr(STAGE2_MEMBER, b"gravity-boot-bin")

            output = root / "merged-esp"
            assemble(esp, stage2, output)

            for relative in REQUIRED_FILES:
                self.assertEqual((output / relative).read_bytes(), relative.encode())
            self.assertEqual((output / "m1n1/boot.bin").read_bytes(), b"gravity-boot-bin")

    def test_rejects_unsafe_archive_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            esp = root / "nixos-esp"
            for relative in REQUIRED_FILES:
                path = esp / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test")

            stage2 = root / "stage2.zip"
            with zipfile.ZipFile(stage2, "w") as archive:
                archive.writestr(STAGE2_MEMBER, b"gravity-boot-bin")
                archive.writestr("esp/../outside", b"bad")

            with self.assertRaisesRegex(ValueError, "unsafe path"):
                assemble(esp, stage2, root / "merged-esp")

    def test_makes_gravity_installer_zip_with_expected_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            esp = root / "nixos-esp"
            for relative in REQUIRED_FILES:
                path = esp / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(relative.encode())

            stage2 = root / "stage2.zip"
            with zipfile.ZipFile(stage2, "w") as archive:
                archive.writestr(STAGE2_MEMBER, b"gravity-boot-bin")

            root_image = root / "root.img"
            root_image.write_bytes(b"N" * 4096)
            output = root / "nixos-gravity-j773g.zip"
            make_package(esp, stage2, root_image, output)

            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("root.img"), b"N" * 4096)
                self.assertEqual(archive.read("esp/m1n1/boot.bin"), b"gravity-boot-bin")
                self.assertIn("esp/EFI/Linux/nixos-gravity.efi", archive.namelist())
                self.assertIn("BOOT-SOURCES.json", archive.namelist())

    def test_rejects_unaligned_root_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "root.img"
            image.write_bytes(b"not-aligned")
            with self.assertRaisesRegex(ValueError, "multiple of 4 KiB"):
                make_package(root / "esp", root / "stage2.zip", image, root / "out.zip")

    def test_refuses_to_overwrite_existing_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            esp = root / "nixos-esp"
            for relative in REQUIRED_FILES:
                path = esp / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"existing source")

            stage2 = root / "stage2.zip"
            with zipfile.ZipFile(stage2, "w") as archive:
                archive.writestr(STAGE2_MEMBER, b"gravity-boot-bin")
            image = root / "root.img"
            image.write_bytes(b"R" * 4096)
            output = root / "existing.zip"
            output.write_bytes(b"keep this file")

            with self.assertRaises(FileExistsError):
                make_package(esp, stage2, image, output)
            self.assertEqual(output.read_bytes(), b"keep this file")


if __name__ == "__main__":
    unittest.main()
