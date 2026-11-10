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
    in
    {
      nixosConfigurations.j773g = j773g;

      packages.${system} = {
        inherit (j773g.config.system.build) toplevel;
        kernel = j773g.config.boot.kernelPackages.kernel;
        root-image = rootImage;
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

        j773g-evaluation = j773g.config.system.build.toplevel;
        j773g-root-image = rootImage;
      };

    };
}
