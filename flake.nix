{
  description = "Home Manager configuration of groscoe";

  inputs = {
    # Specify the source of Home Manager and Nixpkgs.
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-25.11-darwin";
    nixpkgs-stable.url = "flake:nixpkgs";
    home-manager = {
      url = "github:nix-community/home-manager/release-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    darwin = {
      url = "github:LnL7/nix-darwin/nix-darwin-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { nixpkgs, nixpkgs-stable, home-manager, darwin, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      emacsOverlay = import (builtins.fetchTarball {
        url = "https://github.com/nix-community/emacs-overlay/archive/c4b02b4be54b35b6bf0cd6b33ef01e33b5a041af.tar.gz";
        sha256 = "0ngikjszmi2rdjdasbhj04h3cj6waq8f9ijmawz34188pk32lmy4";
      });
      overlays = [
        emacsOverlay
        (final: prev: {
          direnv = prev.direnv.overrideAttrs (old: {
            doCheck = old.doCheck or true && !prev.stdenv.hostPlatform.isDarwin;
          });
        })
      ];
      pkgsFor = system: import nixpkgs {
        inherit system;
        config = { allowUnfree = true; };
        inherit overlays;
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
          extraSpecialArgs = { inherit pkgs-stable; };
        };
    in {
      homeConfigurations = {
        groscoe = configurationFor "x86_64-linux";
        groscoe-linux = configurationFor "x86_64-linux";
        groscoe-darwin = configurationFor "aarch64-darwin";
      };

      packages = forAllSystems (system: {
        default = (configurationFor "${system}").activationPackage;
        home-manager-activation = (configurationFor "${system}").activationPackage;
      });

      darwinConfigurations.groscoe-macos = darwin.lib.darwinSystem {
        system = "aarch64-darwin";
        modules = [
          home-manager.darwinModules.home-manager
          {
            nixpkgs = {
              config.allowUnfree = true;
              inherit overlays;
            };

            system = {
              stateVersion = 6;
              primaryUser = "groscoe";
            };
            ids.gids.nixbld = 30000;

            users.users.groscoe.home = "/Users/groscoe";

            nix.optimise.automatic = true;
            nix.settings = {
              "experimental-features" = [ "nix-command" "flakes" ];
              "build-users-group" = "nixbld";
              "trusted-public-keys" = [
                "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
                "hydra.iohk.io:f/Ea+s+dFdN+3Y/G+FDgSq+a5NEWhJGzdjvKNGv0/EQ="
                "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
              ];
              substituters = [
                "https://cache.nixos.org"
                "https://cache.iog.io"
              ];
              "allow-import-from-derivation" = true;
              "max-jobs" = "auto";
              "keep-failed" = false;
              "keep-going" = true;
            };

            homebrew = {
              enable = true;
              onActivation = {
                autoUpdate = true;
                upgrade = true;
                cleanup = "none";
              };
              brews = [
                "aria2"
                "mosh"
                "podman"
                "typst"
                "yt-dlp"
              ];
              casks = [
                "anki"
                "codex"
                "cursor"
                "iterm2"
                "maccy"
                "skim"
                "wireshark-app"
              ];
            };

            # mosh-server is spawned via ssh on demand, not as a long-lived daemon.
            services.openssh.enable = true;

            home-manager = {
              useGlobalPkgs = true;
              useUserPackages = true;
              extraSpecialArgs = {
                pkgs-stable = pkgsStableFor "aarch64-darwin";
              };
              users.groscoe = import ./home.nix;
            };
          }
        ];
      };
    };
}
