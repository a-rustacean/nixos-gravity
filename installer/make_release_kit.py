#!/usr/bin/env python3
"""Package a pinned Gravity macOS installer runtime for a NixOS device kit."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
import zipfile

import devices
from patch_gravity_urlcache import patch_runtime as patch_urlcache_runtime
from patch_gravity_volbootable import patch_runtime as patch_volbootable_runtime
from patch_gravity_preboot_chflags import patch_runtime as patch_preboot_chflags_runtime


HERE = Path(__file__).resolve().parent
RUNTIME_SOURCE = json.loads((HERE / "runtime-source.json").read_text())
BOOT_SOURCES = json.loads((HERE / "boot-sources.json").read_text())
INSTALLER_DATA = HERE / "installer_data.json"
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


def is_appledouble_path(path: str | PurePosixPath) -> bool:
    """Whether a path is an AppleDouble resource-fork sidecar, hidden by macOS tar."""
    return any(part.startswith("._") for part in PurePosixPath(path).parts)


def safe_extract_runtime(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            path = PurePosixPath(name)
            if "\\" in name or path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe path in pinned Gravity runtime tarball: {name}")
        archive.extractall(destination, filter="data")


def install_command(release_base: str, kit_id: str) -> str:
    return f'''#!/bin/bash
set -euo pipefail

root=$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd -P)
runtime="$root/gravity-installer"
fail() {{ printf '%s\\n' "NixOS Gravity installer: $*" >&2; exit 1; }}

[[ "$(uname -s)" == Darwin ]] || fail 'run this from macOS.'
[[ "$(uname -m)" == arm64 ]] || fail 'only Apple Silicon is supported.'
model=$(/usr/sbin/sysctl -n hw.model 2>/dev/null || true)
[[ -n "$model" ]] || fail 'could not determine this Mac model.'
grep -Fx "$model" "$root/SUPPORTED-MODELS" >/dev/null || {{
    supported=$(tr '\\n' ' ' < "$root/SUPPORTED-MODELS")
    fail "this kit supports $supported, not $model."
}}
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
    kit_id: str,
    version: str,
    output_dir: Path,
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version):
        raise ValueError("version must contain only letters, digits, '.', '_', '+', and '-'")
    kit = devices.kit(kit_id)
    package_name = devices.package_name(kit_id)
    kit_models = [model["product_type"] for model in kit["models"]]
    supported_models = devices.supported_text()
    if not installer_package.is_file() or not gravity_runtime_archive.is_file():
        raise ValueError("installer package and Gravity runtime archive must exist")
    if installer_package.name != package_name:
        raise ValueError(
            f"installer package must be named {package_name}, not {installer_package.name}"
        )
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
    archive_name = f"installer-{version}-{kit_id}.tar.gz"
    output_names = {
        package_name,
        "latest",
        "supported-models.txt",
        archive_name,
        f"{archive_name}.sha256",
        f"{package_name}.sha256",
    }
    conflicts = []
    for name in output_names:
        path = output_dir / name
        if not path.exists() and not path.is_symlink():
            continue
        if name == "supported-models.txt" and path.is_file() and path.read_text() == supported_models:
            continue
        conflicts.append(name)
    if conflicts:
        raise FileExistsError(f"refusing to overwrite existing release assets: {sorted(conflicts)}")

    with tempfile.TemporaryDirectory(prefix="nixos-gravity-release-kit-") as temporary:
        workspace = Path(temporary)
        kit_dir = workspace / "kit"
        kit_dir.mkdir()
        runtime = kit_dir / "gravity-installer"
        runtime.mkdir()
        safe_extract_runtime(gravity_runtime_archive, runtime)
        patch_urlcache_runtime(runtime)
        patch_volbootable_runtime(runtime)
        patch_preboot_chflags_runtime(runtime)

        installer_data = json.loads(INSTALLER_DATA.read_text())
        entry = installer_data["os_list"][0]
        entry["kit"] = kit_id
        entry["models"] = kit_models
        entry["package"] = f"{release_base}/{package_name}"
        (runtime / "installer_data.json").write_text(
            json.dumps(installer_data, indent=2, ensure_ascii=False) + "\n"
        )
        if not (runtime / "install.sh").is_file() or not (runtime / "version.tag").is_file():
            raise ValueError("pinned Gravity runtime archive lacks install.sh or version.tag")

        (kit_dir / "SUPPORTED-MODELS").write_text("\n".join(kit_models) + "\n")
        command = kit_dir / "Install.command"
        command.write_text(install_command(release_base, kit_id))
        command.chmod(0o755)
        provenance = {
            "nixos_gravity_version": version,
            "gravity_installer": RUNTIME_SOURCE,
            "gravity_boot_sources": BOOT_SOURCES,
            "device_kit": {
                "id": kit_id,
                "name": kit["name"],
                "models": kit_models,
            },
            "installer_package": {
                "name": package_name,
                "sha256": sha256(installer_package),
            },
        }
        (kit_dir / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n")

        checksum_lines = []
        for path in sorted(kit_dir.rglob("*")):
            relative_path = path.relative_to(kit_dir).as_posix()
            if path.is_file() and not is_appledouble_path(relative_path):
                checksum_lines.append(f"{sha256(path)}  {relative_path}")
        (kit_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n")

        staged_package = workspace / package_name
        shutil.copyfile(installer_package, staged_package)
        staged_archive = workspace / archive_name
        with tarfile.open(staged_archive, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            archive.add(kit_dir / "Install.command", arcname="Install.command")
            archive.add(kit_dir / "PROVENANCE.json", arcname="PROVENANCE.json")
            archive.add(kit_dir / "SHA256SUMS", arcname="SHA256SUMS")
            archive.add(kit_dir / "SUPPORTED-MODELS", arcname="SUPPORTED-MODELS")
            archive.add(runtime, arcname="gravity-installer", recursive=True)

        staged_latest = workspace / "latest"
        staged_latest.write_text(f"{version}\n")
        (workspace / "supported-models.txt").write_text(supported_models)
        (workspace / f"{archive_name}.sha256").write_text(
            f"{sha256(staged_archive)}  {archive_name}\n"
        )
        (workspace / f"{package_name}.sha256").write_text(
            f"{sha256(staged_package)}  {package_name}\n"
        )
        verify_release_assets(workspace, version, kit_id)

        for name in sorted(output_names):
            shutil.copyfile(workspace / name, output_dir / name)


def verify_release_assets(output_dir: Path, version: str, kit_id: str) -> None:
    kit = devices.kit(kit_id)
    package_name = devices.package_name(kit_id)
    archive_name = f"installer-{version}-{kit_id}.tar.gz"
    with tarfile.open(output_dir / archive_name, "r:gz") as archive:
        names = set(archive.getnames())
        required = {
            "Install.command",
            "PROVENANCE.json",
            "SHA256SUMS",
            "SUPPORTED-MODELS",
            "gravity-installer/installer_data.json",
            "gravity-installer/urlcache.py",
            "gravity-installer/util.py",
            "gravity-installer/fsctl_bootable_helper.py",
            "gravity-installer/stub.py",
            "gravity-installer/preboot_chflags_helper.py",
            "gravity-installer/install.sh",
        }
        missing = required - names
        if missing:
            raise ValueError(f"release kit tarball lacks required files: {sorted(missing)}")
        data = json.load(archive.extractfile("gravity-installer/installer_data.json"))
        entry = data["os_list"][0]
        expected_models = [model["product_type"] for model in kit["models"]]
        if entry.get("kit") != kit_id or entry.get("models") != expected_models:
            raise ValueError("installer metadata does not match the release kit's device manifest")
        package_url = entry["package"]
        if package_url != f"https://github.com/a-rustacean/nixos-gravity/releases/download/{version}/{package_name}":
            raise ValueError("installer metadata package URL does not match this release")
        supported = archive.extractfile("SUPPORTED-MODELS").read().decode()
        if supported != "\n".join(expected_models) + "\n":
            raise ValueError("release kit model list does not match the device manifest")
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
        stub = archive.extractfile("gravity-installer/stub.py").read().decode()
        if "preboot_chflags_helper.py" not in stub or 'flags not in ("schg", "noschg")' not in stub:
            raise ValueError("Gravity Preboot chflags privilege patch is missing")
        preboot_helper = archive.extractfile(
            "gravity-installer/preboot_chflags_helper.py"
        ).read().decode()
        if (
            "def validate_target(path):" not in preboot_helper
            or "def apfs_containers():" not in preboot_helper
            or "protected_stores" not in preboot_helper
            or 'ParentWholeDisk") != "disk0"' not in preboot_helper
        ):
            raise ValueError("privileged Preboot chflags helper is incomplete")

        checksum_file = archive.extractfile("SHA256SUMS").read().decode()
        checksums = {}
        for line in checksum_file.splitlines():
            digest, separator, name = line.partition("  ")
            path = PurePosixPath(name)
            if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("release kit contains a malformed SHA256SUMS entry")
            if path.is_absolute() or ".." in path.parts or name in checksums:
                raise ValueError(f"release kit contains an unsafe or duplicate checksum path: {name}")
            if is_appledouble_path(path):
                raise ValueError(f"release kit must not checksum macOS-hidden AppleDouble metadata: {name}")
            checksums[name] = digest

        regular_files = {
            member.name
            for member in archive.getmembers()
            if member.isfile()
            and member.name != "SHA256SUMS"
            and not is_appledouble_path(member.name)
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

    if (output_dir / "supported-models.txt").read_text() != devices.supported_text():
        raise ValueError("release index does not match the device manifest")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gravity_runtime_archive", type=Path)
    parser.add_argument("installer_package", type=Path)
    parser.add_argument("kit_id")
    parser.add_argument("version")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    make_release_kit(
        args.gravity_runtime_archive,
        args.installer_package,
        args.kit_id,
        args.version,
        args.output_dir,
    )
    print(f"assembled {args.kit_id} release assets in {args.output_dir}")


if __name__ == "__main__":
    main()
