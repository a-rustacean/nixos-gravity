# NixOS Gravity

[![Build](https://github.com/a-rustacean/nixos-gravity/actions/workflows/ci.yml/badge.svg)](https://github.com/a-rustacean/nixos-gravity/actions/workflows/ci.yml)

An experimental NixOS port for the **base M4 Mac mini only** (Mac16,10 / J773g / T8132), reusing Gravity Linux's M4 boot and driver stack. It is not an Asahi Linux installation.

Source: <https://github.com/a-rustacean/nixos-gravity>

Read [`FEASIBILITY.md`](FEASIBILITY.md) before installing. It describes the proposed boot chain, current evidence, hardware risks, and implementation stages.

## Current implementation status

The repository has a pinned Nix flake for a J773g NixOS system, a Gravity Linux 7.1.13 kernel package/config, an ext4 root-image derivation, and a NixOS UKI/ESP tree. CI has successfully built and checksum-verified a pinned Gravity m1n1/U-Boot stage-two artifact for J773g. A follow-on CI job is assembling those boot files with the NixOS ESP and root image in the ZIP layout expected by Gravity's installer. The firmware flow, adapted interactive installer kit, credentials setup, and target-hardware boot/recovery/rollback tests remain outstanding. It is **not a tested NixOS installation kit** yet.

The bootstrap's preflight is safe to run, but a full installation is not ready. The bootstrap script is hosted in this GitHub repository, and the configured release base is GitHub Releases. A complete installer kit has not been published or verified yet. Do not run the install command until a tested kit and recovery guide are released.

The system and root-image derivations target `aarch64-linux`. The [GitHub Actions workflow](.github/workflows/ci.yml) is configured to evaluate and build the current flake outputs on an ARM64 Ubuntu runner. Building locally from macOS still requires an `aarch64-linux` builder.

The intended user flow mirrors Gravity Linux: open Terminal in macOS on the target Mac, run the short command, review the installer plan, and explicitly confirm installation. The eventual kit must verify the exact model, preserve macOS/recovery, reuse the Gravity boot chain, verify downloaded artifacts against a trusted release signature, and provide a tested rollback path. The bootstrap refuses every model except `Mac16,10`.

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

The bootstrap expects release assets named `latest` (containing the kit version), `installer-<version>.tar.gz`, and `installer-<version>.tar.gz.sha256`. The endpoint will fail until those assets exist.
