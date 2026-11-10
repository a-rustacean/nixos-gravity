# NixOS Gravity

An experimental NixOS port for the **base M4 Mac mini only** (Mac16,10 / J773g / T8132), reusing Gravity Linux's M4 boot and driver stack. It is not an Asahi Linux installation.

Read [`FEASIBILITY.md`](FEASIBILITY.md) before installing. It describes the proposed boot chain, current evidence, hardware risks, and implementation stages.

## Current implementation status

The repository now has a pinned Nix flake for a J773g NixOS system, a Gravity Linux 7.1.13 kernel package/config, and an ext4 root-image derivation. The kernel configuration is based on Omarchy-M4-Native's J773g Gravity kernel config; the bootable system still needs a tested EFI/Gravity boot bundle, installer kit, firmware flow, credentials setup, and target-hardware boot tests. It is **not a tested NixOS installation kit** yet.

The bootstrap's preflight is safe to run, but a full installation is not ready. The release host shown below is a proposed stable URL and has not been published or verified. Do not run the install command until the project publishes a tested kit and a recovery guide.

The system and root-image derivations target `aarch64-linux`. Evaluating them works on this Mac, but building them requires an `aarch64-linux` builder; this macOS host has no Linux builder configured.

The intended user flow mirrors Gravity Linux: open Terminal in macOS on the target Mac, run the short command, review the installer plan, and explicitly confirm installation. The eventual kit must verify the exact model, preserve macOS/recovery, reuse the Gravity boot chain, verify downloaded artifacts against a trusted release signature, and provide a tested rollback path. The bootstrap refuses every model except `Mac16,10`.

### Local preflight

From macOS on the base M4 Mac mini, the checked-in bootstrap can currently verify the host without downloading or changing disk contents:

```sh
sh install.sh --preflight
```

## Installation

The release endpoint is not live yet. Once a reviewed installer kit is published there, the intended command will be:

```sh
curl -fsSL https://install.nixos-gravity.org | sh
```
