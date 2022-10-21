{ config, pkgs, ... }:

let
  # ---------------------------------------------------------------------------

  # Configs go here. Don't forget to add to `unManagedConfigs`;

  vim = {
    files = { ".vimrc" = ./vimrc; };
    packages = [ pkgs.rnix-lsp ];
  };

  git = {
    files = {
      ".gitconfig" = ./gitconfig;
      ".git_aliases.sh" = ./git_aliases.sh;
    };

    packages = [ pkgs.diff-so-fancy ];
  };

  nix-tools = { packages = [ pkgs.nixfmt ]; };

  wallpaper = { packages = [ pkgs.variety pkgs.nitrogen ]; };

  # ----------------------------------------------------------------------------

  # Merge all configs together
  toSources = builtins.mapAttrs (_: file: { source = file; });

  build = configs:
    builtins.foldl' (acc:
      { files ? { }, packages ? [ ], ... }: {
        files = acc.files // toSources files;
        packages = acc.packages ++ packages;
      }) {
        files = { };
        packages = [ ];
      } configs;

  unManagedConfigs = build [ vim git nix-tools wallpaper ];
in {
  # Home Manager needs a bit of information about you and the
  # paths it should manage.
  home.username = "groscoe";
  home.homeDirectory = "/home/groscoe";

  # This value determines the Home Manager release that your
  # configuration is compatible with. This helps avoid breakage
  # when a new Home Manager release introduces backwards
  # incompatible changes.
  #
  # You can update Home Manager without changing this value. See
  # the Home Manager release notes for a list of state version
  # changes in each release.
  home.stateVersion = "22.05";

  # Let Home Manager install and manage itself.
  programs.home-manager.enable = true;

  ##
  ## Unmanaged configs
  ##
  home.file = unManagedConfigs.files;
  home.packages = unManagedConfigs.packages;

  ##
  ## Managed configs
  ##

  # Nix-related tools
  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };
}
