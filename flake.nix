{
  description = "Home Manager configuration of groscoe";

  inputs = {
    # Specify the source of Home Manager and Nixpkgs.
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    nixpkgs-stable.url = "flake:nixpkgs";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, nixpkgs-stable, home-manager, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: import nixpkgs {
        inherit system;
        overlays = [
          (import (builtins.fetchTarball {
            url = "https://github.com/nix-community/emacs-overlay/archive/master.tar.gz";
            sha256 = "0fhj0n6favy7yxd3xx242lrsk019yvwpldar7mvizm1fzm4rasn0";
          }))
        ];
      };
      pkgsStableFor = system: nixpkgs-stable.legacyPackages.${system};
      configurationFor = system:
        let
          pkgs = pkgsFor "${system}";
          pkgs-stable = pkgsStableFor "${system}";
        in home-manager.lib.homeManagerConfiguration {
          inherit pkgs;

          # Specify your home configuration modules here, for example,
          # the path to your home.nix.
          modules = [ ./home.nix ];

          # Optionally use extraSpecialArgs
          # to pass through arguments to home.nix
          extraSpecialArgs = { inherit pkgs-stable; is-darwin = pkgs.stdenv.isDarwin; };
        };
    in {
      packages = forAllSystems (system: {
        homeConfigurations.groscoe= configurationFor "${system}";
      });
    };
}
