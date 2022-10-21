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

  nix-tools = {
    packages = [
      pkgs.nixfmt # formatter
      pkgs.cntr # container debugging tool
    ];
  };

  wallpaper = { packages = [ pkgs.variety pkgs.nitrogen ]; };

  # ----------------------------------------------------------------------------

  toSources = builtins.mapAttrs
    (_: file: if builtins.isAttrs file then file else { source = file; });

  # Merge all configs together
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

  # Rofi (drun-style launcher)
  programs.rofi = {
    # See: https://github.com/nix-community/home-manager/blob/master/modules/programs/rofi.nix
    enable = true;

    plugins = [
      pkgs.rofi-calc
      pkgs.rofi-bluetooth
      pkgs.rofi-file-browser
      pkgs.rofi-power-menu
      pkgs.rofi-pulse-select
    ];

    font = "Source Code Pro 24";

    cycle = true; # cycle through the result list

    theme = "solarized_alternate";

    extraConfig = {
      #modes = "drun,run,window,power-menu,bluetooth,pulse-select,file-browser-extended,calc";
      modes = "drun,run,window,file-browser-extended,calc";
      drun-use-desktop-cache = true;
      drun-reload-desktop-cache = true;
    };
  };

  # Nix-related tools
  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };
}
