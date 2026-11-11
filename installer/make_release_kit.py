#!/usr/bin/env python3
"""Package a pinned Gravity macOS installer runtime for the NixOS OS entry."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
import zipfile

from patch_gravity_urlcache import patch_runtime as patch_urlcache_runtime
from patch_gravity_volbootable import patch_runtime as patch_volbootable_runtime


HERE = Path(__file__).resolve().parent
RUNTIME_SOURCE = json.loads((HERE / "runtime-source.json").read_text())
BOOT_SOURCES = json.loads((HERE / "boot-sources.json").read_text())
INSTALLER_DATA = HERE / "installer_data.json"
PACKAGE_NAME = "nixos-gravity-j773g.zip"
REQUIRED_PACKAGE_MEMBERS = {
    "root.img",
    "BOOT-SOURCES.json",
    "esp/EFI/BOOT/BOOTAA64.EFI",
    "esp/EFI/Linux/nixos-gravity.efi",
    "esp/m1n1/boot.bin",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_runtime(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            path = PurePosixPath(name)
            if "\\" in name or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe path in pinned Gravity runtime tarball: {name}")
        archive.extractall(destination, filter="data")


def install_command(release_base: str) -> str:
    return f'''#!/bin/bash
set -euo pipefail

root=$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd -P)
runtime="$root/gravity-installer"
fail() {{ printf '%s\\n' "NixOS Gravity installer: $*" >&2; exit 1; }}

[[ "$(uname -s)" == Darwin ]] || fail 'run this from macOS.'
[[ "$(uname -m)" == arm64 ]] || fail 'only Apple Silicon is supported.'
[[ "$(/usr/sbin/sysctl -n hw.model 2>/dev/null || true)" == Mac16,10 ]] || \\
    fail 'only the base M4 Mac mini (Mac16,10 / J773g) is supported.'
[[ "$(/usr/bin/id -u)" != 0 ]] || fail 'run as your normal macOS user, without sudo.'
[[ -f "$runtime/installer_data.json" && -x "$runtime/install.sh" ]] || \\
    fail 'the bundled Gravity installer runtime is incomplete.'

export INSTALLER_BASE={release_base!r}
export INSTALLER_DATA="$runtime/installer_data.json"
export REPO_BASE={release_base!r}
export PATH="$runtime/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "$runtime"
exec ./install.sh "$@"
'''


def make_release_kit(
    gravity_runtime_archive: Path,
    installer_package: Path,
    version: str,
    output_dir: Path,
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version):
        raise ValueError("version must contain only letters, digits, '.', '_', '+', and '-'")
    if not installer_package.is_file() or not gravity_runtime_archive.is_file():
        raise ValueError("installer package and Gravity runtime archive must exist")
    if sha256(gravity_runtime_archive) != RUNTIME_SOURCE["sha256"]:
        raise ValueError("Gravity installer runtime archive SHA-256 does not match the pin")
    if BOOT_SOURCES["gravity_installer"]["revision"] != RUNTIME_SOURCE["revision"]:
        raise ValueError("Gravity runtime and installer source revisions do not match")

    with zipfile.ZipFile(installer_package) as package:
        names = set(package.namelist())
        missing = REQUIRED_PACKAGE_MEMBERS - names
        if missing:
            raise ValueError(f"NixOS package lacks required members: {sorted(missing)}")
        if package.getinfo("root.img").file_size == 0 or package.getinfo("root.img").file_size % 4096:
            raise ValueError("NixOS root image must be non-empty and 4 KiB aligned")

    release_base = f"https://github.com/a-rustacean/nixos-gravity/releases/download/{version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"installer-{version}.tar.gz"
    output_names = {
        PACKAGE_NAME,
        "latest",
        archive_name,
        f"{archive_name}.sha256",
        f"{PACKAGE_NAME}.sha256",
    }
    conflicts = sorted(
        name for name in output_names if (output_dir / name).exists() or (output_dir / name).is_symlink()
    )
    if conflicts:
        raise FileExistsError(f"refusing to overwrite existing release assets: {conflicts}")

    with tempfile.TemporaryDirectory(prefix="nixos-gravity-release-kit-") as temporary:
        workspace = Path(temporary)
        kit = workspace / "kit"
        kit.mkdir()
        runtime = kit / "gravity-installer"
        runtime.mkdir()
        safe_extract_runtime(gravity_runtime_archive, runtime)
        patch_urlcache_runtime(runtime)
        patch_volbootable_runtime(runtime)

        installer_data = json.loads(INSTALLER_DATA.read_text())
        installer_data["os_list"][0]["package"] = f"{release_base}/{PACKAGE_NAME}"
        (runtime / "installer_data.json").write_text(
            json.dumps(installer_data, indent=2, ensure_ascii=False) + "\n"
        )
        if not (runtime / "install.sh").is_file() or not (runtime / "version.tag").is_file():
            raise ValueError("pinned Gravity runtime archive lacks install.sh or version.tag")

        command = kit / "Install.command"
        command.write_text(install_command(release_base))
        command.chmod(0o755)
        provenance = {
            "nixos_gravity_version": version,
            "gravity_installer": RUNTIME_SOURCE,
            "gravity_boot_sources": BOOT_SOURCES,
            "installer_package": {
                "name": PACKAGE_NAME,
                "sha256": sha256(installer_package),
            },
        }
        (kit / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n")

        checksum_lines = []
        for path in sorted(kit.rglob("*")):
            if path.is_file():
                checksum_lines.append(f"{sha256(path)}  {path.relative_to(kit).as_posix()}")
        (kit / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n")

        staged_package = workspace / PACKAGE_NAME
        shutil.copyfile(installer_package, staged_package)
        staged_archive = workspace / archive_name
        with tarfile.open(staged_archive, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            archive.add(kit / "Install.command", arcname="Install.command")
            archive.add(kit / "PROVENANCE.json", arcname="PROVENANCE.json")
            archive.add(kit / "SHA256SUMS", arcname="SHA256SUMS")
            archive.add(runtime, arcname="gravity-installer", recursive=True)

        staged_latest = workspace / "latest"
        staged_latest.write_text(f"{version}\n")
        (workspace / f"{archive_name}.sha256").write_text(
            f"{sha256(staged_archive)}  {archive_name}\n"
        )
        (workspace / f"{PACKAGE_NAME}.sha256").write_text(
            f"{sha256(staged_package)}  {PACKAGE_NAME}\n"
        )
        verify_release_assets(workspace, version)

        for name in sorted(output_names):
            shutil.copyfile(workspace / name, output_dir / name)


def verify_release_assets(output_dir: Path, version: str) -> None:
    archive_name = f"installer-{version}.tar.gz"
    with tarfile.open(output_dir / archive_name, "r:gz") as archive:
        names = set(archive.getnames())
        required = {
            "Install.command",
            "PROVENANCE.json",
            "SHA256SUMS",
            "gravity-installer/installer_data.json",
            "gravity-installer/urlcache.py",
            "gravity-installer/util.py",
            "gravity-installer/fsctl_bootable_helper.py",
            "gravity-installer/install.sh",
        }
        missing = required - names
        if missing:
            raise ValueError(f"release kit tarball lacks required files: {sorted(missing)}")
        data = json.load(archive.extractfile("gravity-installer/installer_data.json"))
        package_url = data["os_list"][0]["package"]
        if package_url != f"https://github.com/a-rustacean/nixos-gravity/releases/download/{version}/{PACKAGE_NAME}":
            raise ValueError("installer metadata package URL does not match this release")
        urlcache = archive.extractfile("gravity-installer/urlcache.py").read().decode()
        if "_request_path(self.url)" not in urlcache:
            raise ValueError("Gravity URLCache redirect-query patch is missing")
        util = archive.extractfile("gravity-installer/util.py").read().decode()
        if "fsctl_bootable_helper.py" not in util or "errno.EPERM" not in util:
            raise ValueError("Gravity VolBootable privilege patch is missing")
        helper = archive.extractfile(
            "gravity-installer/fsctl_bootable_helper.py"
        ).read().decode()
        if "def validate_target(path):" not in helper or "APFSIOC_VOL_BOOTABLE" not in helper:
            raise ValueError("privileged VolBootable helper is incomplete")

        checksum_file = archive.extractfile("SHA256SUMS").read().decode()
        checksums = {}
        for line in checksum_file.splitlines():
            digest, separator, name = line.partition("  ")
            path = PurePosixPath(name)
            if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("release kit contains a malformed SHA256SUMS entry")
            if path.is_absolute() or ".." in path.parts or name in checksums:
                raise ValueError(f"release kit contains an unsafe or duplicate checksum path: {name}")
            checksums[name] = digest

        regular_files = {
            member.name
            for member in archive.getmembers()
            if member.isfile() and member.name != "SHA256SUMS"
        }
        missing_checksums = regular_files - checksums.keys()
        if missing_checksums:
            raise ValueError(f"release kit lacks checksums for files: {sorted(missing_checksums)}")

        with tempfile.TemporaryDirectory(prefix="nixos-gravity-verify-kit-") as temporary:
            archive.extractall(temporary, filter="data")
            root = Path(temporary)
            for name, expected in checksums.items():
                path = root.joinpath(*PurePosixPath(name).parts)
                if not path.is_file() or sha256(path) != expected:
                    raise ValueError(f"release kit checksum failed for {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gravity_runtime_archive", type=Path)
    parser.add_argument("installer_package", type=Path)
    parser.add_argument("version")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    make_release_kit(
        args.gravity_runtime_archive,
        args.installer_package,
        args.version,
        args.output_dir,
    )
    print(f"assembled versioned test-release assets in {args.output_dir}")


if __name__ == "__main__":
    main()
