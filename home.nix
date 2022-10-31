{ config, pkgs, ... }:

let
  # ---------------------------------------------------------------------------

  # Configs go here. Don't forget to add to `unManagedConfigs`;

  bash = {
    files = {
      ".bashrc" = ./bashrc;
      ".bash_aliases" = ./bash_aliases;
      ".fzf.bash" = ./bash-fzf.bash;
    };
  };

  fish = {
    files = {
      ".config/fish/config.fish" = ./fish-config.fish;
      ".config/fish/functions/fish_user_key_bindings.fish" =
        ./fish-user-keybindings.fish;
      ".config/fish/functions/rprompt.fish" = ./fish-rprompt.fish;
    };
  };

  git = {
    files = {
      ".gitconfig" = ./gitconfig;
      ".git_aliases.sh" = ./git_aliases.sh;
    };

    packages = [ pkgs.diff-so-fancy ];
  };

  haskell = { files = { ".ghc/ghci.conf" = ./haskell-ghci.conf; }; };

  i3 = { files = { ".config/i3/config" = ./i3-config; }; };

  nix-tools = {
    packages = [
      pkgs.nixfmt # formatter
      pkgs.cntr # container debugging tool
      pkgs.cachix # binary caches
      pkgs.direnv # direnv
    ];
  };

  notifications = {
    files = {
      ".config/deadd/deadd.conf" = ./deadd.conf;
      ".config/deadd/deadd.css" = ./deadd.css;
    };
  };

  picom = { files = { ".config/picom/picom.conf" = ./picom.conf; }; };

  #polybar = {
  #  # NOTE: weird inconsistencies.
  #  # packages = [
  #  #   pkgs.polybar
  #  # ];

  #  files = { ".config/polybar/config" = ./polybar; };
  #};

  ripgrep = { files = { ".ripgreprc" = ./ripgreprc; }; };

  rofi = {
    # NOTE: Managed version doesn't find .desktop files that weren't installed
    # with nix.
    files = {
      ".config/rofi/config.rasi" = ./rofi.rasi;
      ".config/rofi/file-browser" = ./rofi-file-browser;
    };
  };

  terminals = {
    files = {
      ".tmux.conf" = ./tmux.conf;
      ".config/guake/guake.con" = ./guake.conf;
    };
  };

  vim = {
    files = {
      ".vimrc" = ./vimrc;
      ".vim/coc-settings.json" = ./vim-coc-settings.json;
    };
    packages = [ pkgs.rnix-lsp ];
  };

  wallpaper = { packages = [ pkgs.variety pkgs.nitrogen ]; };

  # NOTE: Enabled configs must be added here!
  unManagedConfigs = build [
    bash
    fish
    git
    haskell
    i3
    nix-tools
    notifications
    picom
    # polybar
    ripgrep
    rofi
    terminals
    wallpaper
    vim
  ];

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

  # # Rofi (drun-style launcher)
  # programs.rofi = {
  #   # See: https://github.com/nix-community/home-manager/blob/master/modules/programs/rofi.nix
  #   enable = true;

  #   plugins = [
  #     pkgs.rofi-calc
  #     pkgs.rofi-bluetooth
  #     pkgs.rofi-file-browser
  #     pkgs.rofi-power-menu
  #     pkgs.rofi-pulse-select
  #   ];

  #   font = "Source Code Pro 24";

  #   cycle = true; # cycle through the result list

  #   theme = "solarized_alternate";

  #   extraConfig = {
  #     #modes = "drun,run,window,power-menu,bluetooth,pulse-select,file-browser-extended,calc";
  #     modes = "drun,run,window,file-browser-extended,calc";
  #     drun-use-desktop-cache = true;
  #     drun-reload-desktop-cache = true;
  #   };
  # };

  # Newsboat (RSS feed reader)
  programs.newsboat = {
    enable = true;
    urls = import ./newsboat-urls.nix;
    autoReload = true;
    extraConfig = ''
      # unbind keys
      # unbind-key ENTER
      unbind-key j
      unbind-key k
      unbind-key J
      unbind-key K

      # bind keys - vim style
      bind-key j down
      bind-key k up
      bind-key l open
      bind-key h quit
    '';
  };

  # Nix-related tools
  programs.direnv = {
    enable = true;
    nix-direnv.enable = true;
  };
}
