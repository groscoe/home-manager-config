{
  description = "Shared Home Manager configuration with explicit xps and mbp profiles";
  inputs = {
    # Preserve each machine's existing package revisions during consolidation.
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-25.11-darwin";
    nixpkgs-darwin.url = "github:nixos/nixpkgs/nixpkgs-25.11-darwin";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    zen-browser = {
      url = "github:0xc000022070/zen-browser-flake";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
      inputs.home-manager.follows = "home-manager";
    };
    nixpkgs-stable.url = "flake:nixpkgs";
    nixgl = {
      url = "github:nix-community/nixGL";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager/release-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    darwin = {
      url = "github:LnL7/nix-darwin/nix-darwin-25.11";
      inputs.nixpkgs.follows = "nixpkgs-darwin";
    };
  };
  outputs = inputs@{ nixpkgs, nixpkgs-darwin, nixpkgs-stable, nixpkgs-unstable, home-manager, darwin, ... }:
    let
      sharedOverlays = import ./overlays;
      hosts = {
        xps = {
          system = "x86_64-linux";
          source = nixpkgs;
          overlays = [ (import ./hosts/xps/overlay.nix { inherit nixpkgs-unstable; }) ];
        };
        mbp = {
          system = "aarch64-darwin";
          source = nixpkgs-darwin;
          overlays = [ ];
        };
      };
      pkgsFor = host: import hosts.${host}.source {
        inherit (hosts.${host}) system;
        config.allowUnfree = true;
        overlays = sharedOverlays ++ hosts.${host}.overlays;
      };
      argsFor = host: {
        hostName = host;
        pkgs-stable = nixpkgs-stable.legacyPackages.${hosts.${host}.system};
      } // nixpkgs.lib.optionalAttrs (host == "xps") {
        nixGLPackages = inputs.nixgl.packages;
        pkgs-unstable = import nixpkgs-unstable {
          system = hosts.xps.system;
          config.allowUnfree = true;
        };
        zenPackage = inputs.zen-browser.packages.${hosts.xps.system}.beta;
      };
      modulesFor = host: [ ./home.nix (./hosts + "/${host}/home.nix") ];
      homeFor = host: home-manager.lib.homeManagerConfiguration {
        pkgs = pkgsFor host;
        modules = modulesFor host;
        extraSpecialArgs = argsFor host;
      };
      homeProfiles = { xps = homeFor "xps"; mbp = homeFor "mbp"; };
      vmHome = home-manager.lib.homeManagerConfiguration {
        pkgs = pkgsFor "xps";
        modules = modulesFor "xps" ++ [ ./hardware-profile/vm.nix ];
        extraSpecialArgs = argsFor "xps";
      };
      hardwareChecks = (pkgsFor "xps").callPackage ./hardware-profile/check.nix {
        physical = homeProfiles.xps;
        virtual = vmHome;
      };
      xpsHost = (pkgsFor "xps").callPackage ./hosts/xps/ubuntu { };
      xpsRestore = (pkgsFor "xps").callPackage ./validation/vm {
        qemu = (pkgsFor "xps").qemu.override { hostCpuOnly = true; };
      };
      macSystem = darwin.lib.darwinSystem {
        system = hosts.mbp.system;
        modules = [
          home-manager.darwinModules.home-manager
          ./hosts/mbp/system.nix
          {
            nixpkgs.pkgs = pkgsFor "mbp";
            home-manager = {
              useGlobalPkgs = true;
              useUserPackages = true;
              extraSpecialArgs = argsFor "mbp";
              users.groscoe.imports = modulesFor "mbp";
            };
          }
        ];
      };
    in {
      homeConfigurations = homeProfiles // {
        xps-vm = vmHome;
        # Keep existing commands working while making the host names canonical.
        groscoe = homeProfiles.xps;
        groscoe-linux = homeProfiles.xps;
        groscoe-darwin = homeProfiles.mbp;
      };
      darwinConfigurations = { mbp = macSystem; groscoe-macos = macSystem; };
      devShells.x86_64-linux = import ./hosts/xps/dev-shells.nix {
        pkgs = import nixpkgs-unstable { system = hosts.xps.system; };
      };
      apps.x86_64-linux.xps-restore-test = {
        type = "app";
        program = "${xpsRestore}/bin/xps-restore-test";
      };
      apps.x86_64-linux.xps-host = {
        type = "app";
        program = "${xpsHost}/bin/xps-host";
      };
      checks = {
        x86_64-linux = {
          home-profile = homeProfiles.xps.activationPackage;
          vm-home-profile = vmHome.activationPackage;
          hardware-profiles = hardwareChecks;
          personal-scripts = (pkgsFor "xps").callPackage ./validation { };
          xps-host = xpsHost.tests;
          restore-vm = xpsRestore.tests;
        };
        aarch64-darwin = {
          home-profile = homeProfiles.mbp.activationPackage;
          system-profile = macSystem.system;
          personal-scripts = (pkgsFor "mbp").callPackage ./validation { };
        };
      };
      packages = {
        x86_64-linux = {
          default = homeProfiles.xps.activationPackage;
          home-manager-activation = homeProfiles.xps.activationPackage;
          xps-host = xpsHost;
          xps-restore-test = xpsRestore;
        };
        aarch64-darwin = {
          default = homeProfiles.mbp.activationPackage;
          home-manager-activation = homeProfiles.mbp.activationPackage;
        };
      };
    };
}
