{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.hardware.gravity.j773g;
in
{
  options.hardware.gravity.j773g.enable = lib.mkEnableOption "Gravity Linux support for the base M4 Mac mini (J773g / T8132)";

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = pkgs.stdenv.hostPlatform.system == "aarch64-linux";
        message = "hardware.gravity.j773g requires nixpkgs.hostPlatform = \"aarch64-linux\".";
      }
    ];

    hardware.deviceTree = {
      enable = true;
      filter = "t8132-j773g.dtb";
    };

    boot.initrd.systemd.enable = true;
    boot.initrd.systemd.tpm2.enable = false;
    boot.initrd.compressor = "gzip";
    # The base M4 Mac mini boots from Apple's built-in NVMe controller. The
    # generic NixOS initrd module set includes AHCI/SATA drivers that this
    # Gravity kernel intentionally does not build, which makes module closure
    # checks fail and is unnecessary for this target.
    boot.initrd.includeDefaultModules = false;
    # ext4 handles ext2 filesystems in this kernel; there is no separate
    # CONFIG_EXT2_FS module to include in the initrd.
    boot.initrd.availableKernelModules.ext2 = lib.mkForce false;

    boot.kernelParams = [
      "idle=nop"
      "nohlt"
      "arm64.nowfxt"
      "efi=noruntime"
      "nvme_apple.flush_interval=0"
      "systemd.gpt_auto=0"
      "rd.systemd.gpt_auto=0"
      "log_buf_len=1M"
    ];
    boot.consoleLogLevel = 4;

    hardware.enableRedistributableFirmware = false;
  };
}
