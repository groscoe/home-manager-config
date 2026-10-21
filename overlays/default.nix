let
  emacsOverlay = import (builtins.fetchTarball {
    url = "https://github.com/nix-community/emacs-overlay/archive/c4b02b4be54b35b6bf0cd6b33ef01e33b5a041af.tar.gz";
    sha256 = "0ngikjszmi2rdjdasbhj04h3cj6waq8f9ijmawz34188pk32lmy4";
  });
in [
  emacsOverlay
  (_final: prev: {
    direnv = prev.direnv.overrideAttrs (old: {
      doCheck = old.doCheck or true && !prev.stdenv.hostPlatform.isDarwin;
    });
  })
]
