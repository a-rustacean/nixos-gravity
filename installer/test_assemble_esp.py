#!/usr/bin/env python3
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble_esp import REQUIRED_FILES, STAGE2_MEMBER, assemble


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


if __name__ == "__main__":
    unittest.main()
