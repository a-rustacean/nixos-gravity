# NixOS Gravity

[![Build](https://github.com/a-rustacean/nixos-gravity/actions/workflows/ci.yml/badge.svg)](https://github.com/a-rustacean/nixos-gravity/actions/workflows/ci.yml)

An experimental NixOS port for Mac mini (M4) hardware supported by Gravity Linux, reusing Gravity's boot and driver stack. It is not an Asahi Linux installation. **Current Gravity support for the Mac mini covers only the base M4 (Mac16,10 / J773g / T8132); M4 Pro is not included unless Gravity adds support for it.**

Source: <https://github.com/a-rustacean/nixos-gravity>

Read [`FEASIBILITY.md`](FEASIBILITY.md) before installing. It describes the proposed boot chain, current evidence, hardware risks, and implementation stages.

## Current implementation status

The repository has a pinned Nix flake for the currently Gravity-supported Mac mini board, a Gravity kernel package/config, an ext4 root-image derivation, and a NixOS UKI/ESP tree. The installer selects a kit from our explicit Gravity-backed model allowlist; unsupported Macs are rejected. CI must pass for each updated kit, then hardware boot, Apple Recovery, and rollback must be verified. It is **not a tested NixOS installation kit** yet.

The bootstrap's preflight is read-only, but it requires the release model list; a full installation is not ready. The configured release base is GitHub Releases, and a complete installer kit has not been published or hardware-verified. Do not run the install command until a tested kit and recovery guide are released.

The system and root-image derivations target `aarch64-linux`. The [GitHub Actions workflow](.github/workflows/ci.yml) is configured to evaluate and build the current flake outputs on an ARM64 Ubuntu runner. Building locally from macOS still requires an `aarch64-linux` builder.

The intended user flow mirrors Gravity Linux: open Terminal in macOS on the target Mac, run the short command, review the installer plan, and explicitly confirm installation. The eventual kit must verify the exact model against the supported-model list, preserve macOS/recovery, reuse the Gravity boot chain, verify downloaded artifacts against a trusted release signature, and provide a tested rollback path. At present, the supported-model list contains only `Mac16,10`, matching Gravity's current Mac mini M4 support.

### Local preflight

From macOS on the base M4 Mac mini, the checked-in bootstrap can currently verify the host without downloading or changing disk contents:

```sh
sh install.sh --preflight
```

## Installation

Once this repository is publicly accessible and a reviewed installer kit is attached to a GitHub Release, the intended command is:

```sh
curl -fsSL https://raw.githubusercontent.com/a-rustacean/nixos-gravity/main/install.sh | sh
```

The bootstrap expects release assets named `latest`, `supported-models.txt`, `installer-<version>-<kit>.tar.gz`, and that archive's `.sha256` checksum. The endpoint will fail until those assets exist.
