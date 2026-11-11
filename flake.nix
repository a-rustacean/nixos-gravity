{
  description = "Experimental NixOS for the base M4 Mac mini (J773g), using Gravity Linux hardware support";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  };

  outputs =
    { self, nixpkgs }:
    let
      system = "aarch64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      j773g = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [ ./configuration.nix ];
      };
      rootImage = pkgs.callPackage "${toString pkgs.path}/nixos/lib/make-ext4-fs.nix" {
        storePaths = [ j773g.config.system.build.toplevel ];
        volumeLabel = "NIXOS";
        uuid = "7a773000-0000-4000-8000-000000000001";
      };
      efiArch = pkgs.stdenv.hostPlatform.efiArch;
      systemdBoot = "${j773g.config.systemd.package}/lib/systemd/boot/efi/systemd-boot${efiArch}.efi";
      uki = j773g.config.system.build.uki;
      ukiFile = j773g.config.system.boot.loader.ukiFile;
      nixosEsp = pkgs.runCommand "nixos-gravity-j773g-esp" { } ''
        mkdir -p "$out/EFI/BOOT" "$out/EFI/Linux" "$out/loader/entries"
        cp ${systemdBoot} "$out/EFI/BOOT/BOOT${pkgs.lib.toUpper efiArch}.EFI"
        cp ${uki}/${ukiFile} "$out/EFI/Linux/nixos-gravity.efi"
        cat > "$out/loader/loader.conf" <<'EOF'
        default nixos-gravity.conf
        timeout 3
        editor no
        EOF
        cat > "$out/loader/entries/nixos-gravity.conf" <<'EOF'
        title NixOS Gravity (J773g)
        efi /EFI/Linux/nixos-gravity.efi
        EOF
        test -s "$out/EFI/BOOT/BOOT${pkgs.lib.toUpper efiArch}.EFI"
        test -s "$out/EFI/Linux/nixos-gravity.efi"
      '';
    in
    {
      nixosConfigurations.j773g = j773g;

      packages.${system} = {
        inherit (j773g.config.system.build) toplevel;
        kernel = j773g.config.boot.kernelPackages.kernel;
        root-image = rootImage;
        nixos-esp = nixosEsp;
        uki = uki;
        default = j773g.config.system.build.toplevel;
      };

      checks.${system} = {
        j773g-kernel-config = pkgs.runCommand "j773g-kernel-config-check" { } ''
          config=${j773g.config.boot.kernelPackages.kernel.configfile}
          grep -q '^CONFIG_ARM64_16K_PAGES=y$' "$config"
          grep -q '^CONFIG_NVME_APPLE=y$' "$config"
          grep -q '^CONFIG_DRM_APPLE=y$' "$config"
          grep -q '^CONFIG_PHY_APPLE_DPTX=y$' "$config"
          grep -q '^CONFIG_DRM_ASAHI_M4=m$' "$config"
          touch "$out"
        '';

        j773g-esp = pkgs.runCommand "j773g-esp-check" { } ''
          test -s ${nixosEsp}/EFI/BOOT/BOOT${pkgs.lib.toUpper efiArch}.EFI
          test -s ${nixosEsp}/EFI/Linux/nixos-gravity.efi
          grep -q 'efi /EFI/Linux/nixos-gravity.efi' ${nixosEsp}/loader/entries/nixos-gravity.conf
          touch "$out"
        '';

        j773g-evaluation = j773g.config.system.build.toplevel;
        j773g-root-image = rootImage;
        j773g-uki = uki;
      };

    };
}
