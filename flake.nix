{
  description = "Shared Home Manager configuration with explicit xps and mbp profiles";
  inputs = {
    # Preserve each machine's existing package revisions during consolidation.
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-25.11-darwin";
    nixpkgs-darwin.url = "github:nixos/nixpkgs/nixpkgs-25.11-darwin";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
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
      };
      modulesFor = host: [ ./home.nix (./hosts + "/${host}/home.nix") ];
      homeFor = host: home-manager.lib.homeManagerConfiguration {
        pkgs = pkgsFor host;
        modules = modulesFor host;
        extraSpecialArgs = argsFor host;
      };
      homeProfiles = { xps = homeFor "xps"; mbp = homeFor "mbp"; };
      xpsHost = (pkgsFor "xps").callPackage ./hosts/xps/ubuntu { };
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
        # Keep existing commands working while making the host names canonical.
        groscoe = homeProfiles.xps;
        groscoe-linux = homeProfiles.xps;
        groscoe-darwin = homeProfiles.mbp;
      };
      darwinConfigurations = { mbp = macSystem; groscoe-macos = macSystem; };
      devShells.x86_64-linux = import ./hosts/xps/dev-shells.nix {
        pkgs = import nixpkgs-unstable { system = hosts.xps.system; };
      };
      apps.x86_64-linux.xps-host = {
        type = "app";
        program = "${xpsHost}/bin/xps-host";
      };
      checks.x86_64-linux.xps-host = xpsHost.tests;
      packages = {
        x86_64-linux = {
          default = homeProfiles.xps.activationPackage;
          home-manager-activation = homeProfiles.xps.activationPackage;
          xps-host = xpsHost;
        };
        aarch64-darwin = {
          default = homeProfiles.mbp.activationPackage;
          home-manager-activation = homeProfiles.mbp.activationPackage;
        };
      };
    };
}
