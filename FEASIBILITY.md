# NixOS on the base M4 Mac mini using Gravity Linux

**Status:** feasibility/design research plus a preflight-only install bootstrap; no installation or target-disk changes made  
**Target:** Mac mini M4, Mac16,10 / J773g / T8132 only  
**Research snapshot:** 2026-11-10

## Executive summary

**Feasible, but experimental.** The M4 Mac mini already boots Gravity Linux, and an independent J773g project has demonstrated the same Gravity-based boot chain with another Linux distribution. NixOS can supply the userspace and system management; it needs a board-specific module and must reuse Gravity's M4-capable bootloader, kernel/device tree, firmware, and (optionally) Mesa stack.

The recommended first architecture is:

> Apple boot stub → Gravity m1n1 → Gravity U-Boot → UEFI boot manager → NixOS kernel/initrd → NixOS root filesystem

Keep the existing macOS installation, startup stub, and Gravity-created EFI System Partition (ESP) during initial bring-up. Use NixOS `systemd-boot` as the first Nix-managed UEFI loader candidate; Omarchy's J773g work has specifically demonstrated **Limine** in this chain, so that is the hardware-proven fallback if U-Boot/systemd-boot compatibility is troublesome. A direct m1n1-to-Linux payload is a viable alternative, but its NixOS precedent is the **M4 MacBook Air J713**, not this Mac mini.

This is not a proposal to use Asahi Linux's NixOS support stack. Gravity's own pinned M4 bootloader/kernel/device-tree and firmware handling are the platform dependency. Some Gravity sources have Asahi/Fedora lineage; the plan is to package Gravity's downstream revisions and patches, not substitute Asahi's M1/M2-oriented boot stack.

## Evidence and confidence

| Area | Finding | Confidence for J773g |
|---|---|---|
| Gravity boot | User already runs Gravity Linux on this machine. Gravity's installer registers an Apple boot stub that chainloads `m1n1/boot.bin` on the ESP. | High |
| m1n1 → U-Boot → Linux bootloader | Omarchy-M4-Native documents this chain on the base M4 mini, including Limine and a UKI. Gravity's UEFI-only workflow builds the m1n1/DTB/U-Boot bundle. | High for the chain; NixOS loader integration remains to test |
| Gravity hardware support | Gravity maintains T8132/J773g support in m1n1, U-Boot, kernel/DTB, and installer firmware handling. | High for boot; individual peripherals vary |
| NixOS integration | Firn demonstrates a NixOS module and generation writer on the M4 MacBook Air J713, using Gravity's installer and m1n1. | Medium; useful precedent, different board and boot route |
| Desktop/peripherals | Gravity's M4 kernel and Mesa include M4-specific work, but this remains an alpha-quality stack with known limitations. | Medium to low; must validate on this exact unit |

Asahi Linux's NixOS project (`nix-community/nixos-apple-silicon`) is not a ready-made route: its current boot/kernel packages and DT properties target the Asahi stack, and it cannot boot this M4 as-is. Its module structure can be borrowed as a design pattern, not its platform packages.

## Proposed architecture

### Primary: Gravity U-Boot followed by a NixOS UEFI loader

1. **Retain the Apple boot registration and Gravity stub.** The installer creates a stub boot object containing m1n1 stage 1 variables, including the ESP identifier and a chainload path. Do not replace or recreate this machinery in the first NixOS prototype.
2. **Keep Gravity's m1n1 stage 2 and U-Boot bundle** at the existing ESP path (`m1n1/boot.bin`). Gravity's UEFI-only build composes m1n1, Apple device trees, and U-Boot. Ensure the bundle includes the T8132/J773g DTB and is pinned to a tested Gravity revision.
3. **Boot a NixOS-managed UEFI loader from U-Boot.** Start with NixOS `systemd-boot`; avoid depending on EFI NVRAM registration until proven. If that path does not work reliably, use Limine, which has an exact-J773g boot precedent, and have NixOS manage its configuration and kernel artifacts.
4. **Keep NixOS on its own Linux root filesystem.** Mount the ESP for boot artifacts and keep the Nix store/root on the Linux root partition. The NixOS kernel, initrd, DTB, and root filesystem must all match the Gravity T8132 hardware support. Keep a bounded number of boot generations: the existing ESP is about 500 MB, and copied kernels/initrds can fill it.
5. **Use the m1n1-provided ESP identity.** A small NixOS module should read `chosen/gravity,efi-system-partition`, resolve the PARTUUID, wait for the device, and mount the ESP. This follows the Gravity property expected by its U-Boot fork; do not use Asahi's `asahi,efi-system-partition` property.

This retains the familiar UEFI flow and NixOS generation model while reusing the boot path already exercised on J773g. It is the best starting point for recovery and iteration, not a claim that every boot-menu interaction is already validated.

### Fallback: direct m1n1 Linux payload

Firn's J713 design writes each generation directly to `m1n1/boot.bin` as m1n1 stage 2 + boot arguments + gzip kernel + DTB + gzip initrd + firmware CPIO. A `firn-boot`-like NixOS generation hook can atomically replace that file while preserving the installer boot image and firmware.

This bypasses U-Boot and the UEFI loader, potentially simplifying the boot chain and avoiding a pre-kernel graphical menu. It also makes the boot writer, payload format, generation rollback, and firmware assembly board-specific. Treat it as a fallback until directly tested on J773g; J713 success does not establish J773g compatibility.

## NixOS work items

1. **Board module:** introduce a dedicated module (for example, `hardware.gravity.j773g`) with an explicit `aarch64-linux` and J773g/T8132 assertion. Do not enable it on M4 Pro/Max or MacBooks.
2. **Kernel package:** package a pinned Gravity kernel and its modules/DTBs using Nix's kernel packaging. Preserve the Gravity M4 patchset and the required 16-KiB page-size configuration; keep module version, kernel image, DTB, and modules in lockstep. Do not substitute stock NixOS or Asahi kernels without a separate hardware qualification.
3. **Boot artifacts:** package Gravity m1n1 and U-Boot and compose the expected `boot.bin`. Set a stable boot configuration and retain a known-good original/fallback. Confirm exact filenames and DTB selection against the currently installed Gravity build before writing the ESP.
4. **Kernel arguments and early boot:** validate the J773g SMP workaround arguments `idle=nop nohlt arm64.nowfxt`; test `efi=noruntime` on the U-Boot route. Keep Plymouth and other early graphics out of initial testing. Evaluate `nvme_apple.flush_interval=0`, but do not treat it as a fix for the reported NVMe issue.
5. **Firmware/calibration:** provide the Apple firmware and per-radio calibration obtained by the Gravity installer/recovery extraction path. The installer keeps `vendorfw/` on the ESP, and Gravity U-Boot has T8132 calibration-injection support. NixOS must make the firmware available to kernel drivers in the expected paths and preserve calibration across rebuilds. Do not redistribute extracted proprietary firmware; extract it on the target machine.
6. **Optional graphics and audio:** package Gravity's M4-capable Mesa and kernel drivers only after a reliable console/root boot. Audio needs separate safe testing; a driver existing in the kernel is not evidence that speaker playback is safe or fully supported.
7. **Generation lifecycle:** integrate the loader with `nixos-rebuild boot`/`switch`, garbage collection, ESP space monitoring, and rollback. A failed generation must leave the previous bootable image intact. Test update interruption and recovery before using the internal disk as the only boot target.
8. **Installer/recovery:** initially build a NixOS image or installer that can boot without repartitioning the internal disk (external storage or a RAM/network-assisted test). Later, adapt the MIT-licensed Gravity installer for a NixOS payload. Preserve macOS Recovery and document a tested return-to-Gravity path.

## Risks and limitations

- **Alpha hardware support:** Gravity's M4 stack is actively evolving. Suspend, USB-C display/Thunderbolt, shutdown/reboot, GPU, and audio behavior may be incomplete or unstable; test each on the target rather than inferring support from a driver being present.
- **Invisible early boot:** Gravity m1n1 is built with `NO_DISPLAY` for M4. U-Boot and the loader may be invisible until the Linux DCP/HDMI driver starts. Use a default/short-timeout boot path and wired networking/log capture; do not make successful interaction with a graphical boot menu a bring-up prerequisite.
- **SMP and EFI runtime:** J773g testing documents `idle=nop nohlt arm64.nowfxt` for reliable multicore startup and `efi=noruntime` for a U-Boot/EFI runtime hang. These are board-sensitive workarounds and should be tested against the exact kernel and boot path.
- **NVMe reliability:** Firn reports Apple NVMe/RTKit crashes during sustained writes on J713, including bursts of a few GB. It may affect other T8132 systems, but the report is not proof of the same failure on J773g. Keep early tests read-mostly, build on another machine, back up first, and investigate before large builds or writes on the mini.
- **Firmware handling:** Apple firmware and calibration are essential and are not ordinary freely redistributable Nix store inputs. The installation/update design must preserve target-extracted files without publishing them.
- **ESP capacity and boot rollback:** the approximately 500-MB ESP is shared boot infrastructure. Unbounded copied NixOS generations, firmware, and installer files can exhaust it. Track usage and define a safe cleanup policy.
- **Changing upstreams and provenance:** pin Gravity kernel, bootloader, U-Boot, Mesa, and installer revisions. Preserve upstream attribution and licenses, review patches when updating, and record which hardware tests validate each pin. Gravity and Asahi are separate projects with differing contribution policies.
- **No established alpha upgrade path:** do not assume an existing Gravity alpha installation can be upgraded in place to a future release. Preserve a recovery route and make backups before changing partitions or boot files.

## Suggested phases

1. **Read-only inventory:** record current Gravity version, partition map, ESP contents/usage, kernel command line, DTB, and boot bundle. Confirm macOS Recovery/restore access and back up the ESP and important data.
2. **Reproducible packages:** build the pinned Gravity kernel, modules, DTB, m1n1, and U-Boot from Nix on an aarch64-linux builder (native or remote). Verify hashes and inspect the generated boot bundle without installing it.
3. **Non-destructive boot test:** boot a minimal NixOS kernel/initrd with wired networking and remote logs, initially from external media or a controlled temporary path. Validate display initialization, SMP, NVMe reads, root mount, and clean reboot before sustained writes.
4. **NixOS module and loader:** implement the board module and generation integration; validate `systemd-boot`, then use Limine if needed. Test failed-generation rollback and ESP-full handling.
5. **Internal installation:** only after recovery and rollback are proven, install to a dedicated Linux root while retaining macOS and the Gravity-created boot infrastructure. Add Wi-Fi/Bluetooth, GPU, and audio in separate test stages.

## Source trail

The conclusions above were checked against these project sources and revisions (upstream projects evolve; re-check pins before implementation):

- [Gravity installer](https://github.com/GravityLinux/installer): `src/osinstall.py`, `src/m1n1.py`, and `.github/workflows/uefi-only-build.yaml` (installer pin `34c9ded9e2e4efd9add6bb984d5c50656ea324da`). The installer records `chosen.gravity,efi-system-partition`, chainloads the ESP `next_object`, copies firmware, and the workflow builds a m1n1/DTB/U-Boot `boot.bin`.
- [Gravity packages](https://github.com/GravityLinux/packages): `sources.json`, `kernel/kernel.spec`, `kernel/gravity.config`, and `UPSTREAM.md`. Research pins include Gravity Linux kernel `dea38a96aa86679d5e24da16b799030fe07ad2f6`, Gravity bootloader `f6c017a7090c3256f9b5587417168a9d40ff5af0`, Gravity Mesa `533a2be53faebfd31080c6b2d2a4dc3351ce7b72`, and the U-Boot patch set ending at `a2f6913694ff26908c16948af3f8372429782263`.
- [Firn](https://github.com/Youwes09/Firn): `modules/boot.nix`, `modules/kernel.nix`, `pkgs/firn-boot/firn-boot.py`, `docs/GUIDE.md`, and `docs/ISSUES.md`. This is the NixOS/J713 direct-payload precedent and source of the documented NVMe issue.
- [Omarchy M4 Mini](https://github.com/andreinita21/OmarchyM4Mini): `docs/j773g-install.md` and `packaging/j773g/`. This documents the exact-J773g m1n1 → U-Boot → Limine → UKI route and J773g boot workarounds.
- [nixos-apple-silicon](https://github.com/nix-community/nixos-apple-silicon): useful examples of NixOS module/boot packaging, but its Asahi stack and `asahi,efi-system-partition` integration are not applicable as-is.
