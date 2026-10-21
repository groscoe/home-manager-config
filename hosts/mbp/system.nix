{ ... }: {
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
    substituters = [ "https://cache.nixos.org" "https://cache.iog.io" ];
    "allow-import-from-derivation" = true;
    "max-jobs" = "auto";
    "keep-failed" = false;
    "keep-going" = true;
  };
  homebrew = {
    enable = true;
    onActivation = { autoUpdate = true; upgrade = true; cleanup = "none"; };
    brews = [ "aria2" "mosh" "podman" "typst" "yt-dlp" ];
    casks = [
      "anki" "battery" "codex" "cursor" "iterm2" "maccy" "mouseless"
      "skim" "shortcat" "trex" "wireshark-app" "xournal++"
    ];
  };
  services.openssh.enable = true;
}
