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
