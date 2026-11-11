#!/usr/bin/env python3
"""Elevate only Gravity's NixOS Preboot immutable-flag update on EPERM."""

import argparse
from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
HELPER_SOURCE = HERE / "preboot_chflags_helper.py"
HELPER_NAME = "preboot_chflags_helper.py"
OLD_METHOD = '''    def chflags(self, flags, path):
        logging.info(f"chflags {flags} {path}")
        subprocess.run(["chflags", flags, path], check=True)
'''
NEW_METHOD = '''    def chflags(self, flags, path):
        logging.info(f"chflags {flags} {path}")
        try:
            subprocess.run(
                ["chflags", flags, path], check=True, capture_output=True, text=True
            )
        except subprocess.CalledProcessError as error:
            if flags not in ("schg", "noschg"):
                raise
            if not any(
                message in (error.stderr or "")
                for message in ("Operation not permitted", "Permission denied")
            ):
                if error.stderr:
                    logging.error(error.stderr.rstrip())
                raise
            # Elevate only this metadata change; the helper validates the exact
            # NixOS Preboot AdminUserRecoveryInfo.plist before invoking chflags.
            runtime = os.path.dirname(os.path.abspath(__file__))
            frameworks = os.path.join(runtime, "Frameworks")
            python_lib = os.path.join(
                frameworks, "Python.framework", "Versions", "Current", "lib"
            )
            helper = os.path.join(runtime, "preboot_chflags_helper.py")
            subprocess.run([
                "/usr/bin/sudo", "/usr/bin/env",
                f"DYLD_FRAMEWORK_PATH={frameworks}",
                f"DYLD_LIBRARY_PATH={python_lib}",
                os.path.abspath(sys.executable), helper, path, flags,
            ], check=True)
'''


def patch_source(source: str) -> str:
    if HELPER_NAME in source:
        if NEW_METHOD in source:
            return source
        raise ValueError("Gravity stub.py contains a partial Preboot chflags patch")
    if source.count(OLD_METHOD) != 1:
        raise ValueError("unexpected Gravity StubInstaller.chflags method")
    return source.replace(OLD_METHOD, NEW_METHOD, 1)


def patch_runtime(runtime: Path) -> None:
    source_file = runtime / "stub.py"
    helper_target = runtime / HELPER_NAME
    if helper_target.exists() and helper_target.read_bytes() != HELPER_SOURCE.read_bytes():
        raise ValueError(f"refusing to overwrite an unexpected runtime helper: {helper_target}")
    source_file.write_text(patch_source(source_file.read_text()))
    if not helper_target.exists():
        shutil.copyfile(HELPER_SOURCE, helper_target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gravity_runtime", type=Path)
    args = parser.parse_args()
    patch_runtime(args.gravity_runtime)
    print(f"patched privileged Preboot chflags handling in {args.gravity_runtime / 'stub.py'}")


if __name__ == "__main__":
    main()
