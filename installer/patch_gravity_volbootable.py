#!/usr/bin/env python3
"""Elevate only Gravity's APFS VolBootable mutation when macOS denies it."""

import argparse
from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
HELPER_SOURCE = HERE / "fsctl_bootable_helper.py"
HELPER_NAME = "fsctl_bootable_helper.py"
OLD_IMPORT = "import re, logging, sys, os, stat, shutil, struct, subprocess, zlib, time, hashlib, lzma\n"
NEW_IMPORT = "import re, logging, sys, os, stat, shutil, struct, subprocess, zlib, time, hashlib, lzma, errno\n"
OLD_FUNCTION = '''c_fsctl = None
def fsctl_apfs_bootable(path, cmd):
    global c_fsctl
    if c_fsctl is None:
        sysdll = CDLL("libSystem.B.dylib", use_errno=True)
        func = sysdll.fsctl
        func.restype = c_int
        func.argtypes = (c_char_p, c_ulong, POINTER(c_int), c_uint)
        c_fsctl = func
    c_cmd = c_int(cmd)
    APFSIOC_VOL_BOOTABLE = 0xc0044a57 # _IOWR('J', 'W', int32_t)
    err = c_fsctl(path.encode(), APFSIOC_VOL_BOOTABLE, byref(c_cmd), 0)
    if err == -1:
        raise Exception(f'fsctl call failed, errno: {get_errno()}')
    return c_cmd.value
'''
NEW_FUNCTION = '''c_fsctl = None
def fsctl_apfs_bootable(path, cmd):
    global c_fsctl
    if c_fsctl is None:
        sysdll = CDLL("libSystem.B.dylib", use_errno=True)
        func = sysdll.fsctl
        func.restype = c_int
        func.argtypes = (c_char_p, c_ulong, POINTER(c_int), c_uint)
        c_fsctl = func
    c_cmd = c_int(cmd)
    APFSIOC_VOL_BOOTABLE = 0xc0044a57 # _IOWR('J', 'W', int32_t)
    err = c_fsctl(path.encode(), APFSIOC_VOL_BOOTABLE, byref(c_cmd), 0)
    if err == -1:
        error = get_errno()
        if cmd in (-1, 1) and error == errno.EPERM:
            # macOS 27 denies this metadata mutation to an ordinary installer process.
            # Elevate only the specific VolBootable ioctl; never run the installer as root.
            runtime = os.path.dirname(os.path.abspath(__file__))
            frameworks = os.path.join(runtime, "Frameworks")
            python_lib = os.path.join(
                frameworks, "Python.framework", "Versions", "Current", "lib"
            )
            helper = os.path.join(runtime, "fsctl_bootable_helper.py")
            subprocess.run([
                "/usr/bin/sudo", "/usr/bin/env",
                f"DYLD_FRAMEWORK_PATH={frameworks}",
                f"DYLD_LIBRARY_PATH={python_lib}",
                os.path.abspath(sys.executable), helper, path, str(cmd),
            ], check=True)
            actual = fsctl_apfs_bootable(path, 0)
            expected = 1 if cmd == 1 else -1
            if actual != expected:
                raise Exception(
                    f"elevated VolBootable update did not stick: expected {expected}, got {actual}"
                )
            return actual
        raise Exception(f'fsctl call failed, errno: {error}')
    return c_cmd.value
'''


def patch_source(source: str) -> str:
    if "fsctl_bootable_helper.py" in source:
        if NEW_IMPORT in source and NEW_FUNCTION in source:
            return source
        raise ValueError("Gravity util.py contains a partial VolBootable privilege patch")

    if source.count(OLD_IMPORT) != 1:
        raise ValueError("unexpected Gravity util.py import layout")
    if source.count(OLD_FUNCTION) != 1:
        raise ValueError("unexpected Gravity APFS VolBootable function")

    return source.replace(OLD_IMPORT, NEW_IMPORT, 1).replace(OLD_FUNCTION, NEW_FUNCTION, 1)


def patch_runtime(runtime: Path) -> None:
    source_file = runtime / "util.py"
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
    print(f"patched privileged VolBootable handling in {args.gravity_runtime / 'util.py'}")


if __name__ == "__main__":
    main()
