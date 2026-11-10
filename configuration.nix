{
  config,
  lib,
  pkgs,
  ...
}:
let
  gravityKernel = pkgs.callPackage ./pkgs/linux { kernelPatches = [ ]; };
in
{
  imports = [ ./modules/j773g.nix ];

  nixpkgs.hostPlatform = "aarch64-linux";

  hardware.gravity.j773g.enable = true;
  boot.kernelPackages = pkgs.linuxPackagesFor gravityKernel;

  networking.hostName = "nixos-m4-mini";
  networking.useDHCP = lib.mkDefault true;
  time.timeZone = "UTC";

  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 2;
  boot.loader.efi.canTouchEfiVariables = false;

  # The installer creates the ESP with this GPT partition name and the root
  # image carries the fixed UUID below. The installer kit must preserve both.
  fileSystems."/" = {
    device = "/dev/disk/by-uuid/7a773000-0000-4000-8000-000000000001";
    fsType = "ext4";
    options = [ "noatime" ];
  };

  fileSystems."/boot" = {
    device = "/dev/disk/by-partlabel/EFI - NixOS Gravity";
    fsType = "vfat";
    options = [ "umask=0077" ];
  };

  users.mutableUsers = true;

  services.openssh.enable = false;
  system.stateVersion = "26.05";
}
