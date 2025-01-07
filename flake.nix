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
        config = { allowUnfree = true; };
        overlays = [
          (import (builtins.fetchTarball {
            url = "https://github.com/nix-community/emacs-overlay/archive/c4b02b4be54b35b6bf0cd6b33ef01e33b5a041af.tar.gz";
            sha256 = "0ngikjszmi2rdjdasbhj04h3cj6waq8f9ijmawz34188pk32lmy4";
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
