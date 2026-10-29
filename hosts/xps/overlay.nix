{ nixpkgs-unstable }:
(_final: prev: prev.lib.optionalAttrs prev.stdenv.hostPlatform.isLinux {
          firefox = nixpkgs-unstable.legacyPackages.${prev.stdenv.hostPlatform.system}.firefox;
          sbsigntool = nixpkgs-unstable.legacyPackages.${prev.stdenv.hostPlatform.system}.sbsigntool;
          # Nixpkgs still ships 1.126; pin the current verified upstream archive.
          # Remove this override once nixpkgs-unstable catches up.
          vscodium = let
            unstable = nixpkgs-unstable.legacyPackages.${prev.stdenv.hostPlatform.system};
          in unstable.vscodium.overrideAttrs (old: {
            version = "1.140.06880";
            src = unstable.fetchurl {
              url = "https://github.com/VSCodium/vscodium/releases/download/1.140.06880/VSCodium-linux-x64-1.140.06880.tar.gz";
              hash = "sha256-YSI7dPnkCDQRcxHsQXfLOG0JuEwark+eZ0yWWAVpzvM=";
            };
            passthru = old.passthru // { vscodeVersion = "1.140.0"; };
            meta = old.meta // {
              changelog = "https://github.com/VSCodium/vscodium/releases/tag/1.140.06880";
            };
          });
        })
