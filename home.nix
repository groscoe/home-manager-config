{ config, pkgs, lib, ... }:

let
  # Configs go here. Don't forget to add to `unManagedConfigs`;
  unManagedConfigs = build (lib.attrValues {
    acpi = { packages = [ pkgs.acpi ]; };

    bash = {
      files = {
        ".bashrc" = ./bash/bashrc;
        ".bash_aliases" = ./bash/bash_aliases;
        ".fzf.bash" = ./bash/fzf.bash;
      };
    };

    # Notifications
    deadd = {
      files = {
        ".config/deadd/deadd.conf" = ./deadd/config/deadd/deadd.conf;
        ".config/deadd/deadd.css" = ./deadd/config/deadd/deadd.css;
      };
    };

    deluge = { packages = [ pkgs.deluge ]; };

    fzf = { packages = [ pkgs.fzf pkgs.fd ]; };

    fonts = { packages = [ pkgs.source-code-pro ]; };

    git = {
      files = {
        ".gitconfig" = ./git/gitconfig;
        ".git_aliases.sh" = ./git/git_aliases.sh;
      };

      packages = [ pkgs.diff-so-fancy ];
    };

    haskell = { files = { ".ghc/ghci.conf" = ./haskell/ghc/ghci.conf; }; };

    i3 = {
      packages = [ pkgs.i3-gaps ];
      files = { ".config/i3/config" = ./i3/config/i3/config; };
    };

    logseq = { packages = [ pkgs.logseq ]; };

    media = {
      packages = [ pkgs.vlc ];
    };

    networking-tools = {
      packages = [ pkgs.lsof pkgs.speedtest-cli pkgs.nethogs ];
    };

    nix-tools = {
      packages = [
        pkgs.nixfmt # formatter
        pkgs.cntr # container debugging tool
        pkgs.cachix # binary caches
        pkgs.direnv # direnv
        pkgs.nix-output-monitor
      ];
    };

    picom = { files = { ".config/picom/picom.conf" = ./picom/config/picom/picom.conf; }; };

    polybar = {
      # NOTE: weird inconsistencies.
      # packages = [ pkgs.polybar ];

      files = { ".config/polybar" = ./polybar/config/polybar; };
    };

    programming-tools = { packages = [ pkgs.comby pkgs.pretty-simple ]; };

    ripgrep = {
      files = { ".ripgreprc" = ./ripgrep/ripgreprc; };
      packages = [ pkgs.ripgrep ];
    };

    rofi = {
      # NOTE: Managed version doesn't find .desktop files that weren't installed
      # with nix.
      files = {
        ".config/rofi/config.rasi" = ./rofi/config/rofi/rofi.rasi;
        ".config/rofi/file-browser" = ./rofi/config/rofi/rofi-file-browser;
      };
    };

    shell-utilities = {
      packages = [
        pkgs.bat
        pkgs.lsd
        pkgs.xclip
      ];
    };

    terminals = {
      packages = [
        # pkgs.alacritty # NOTE: GPU acceleration issues
        pkgs.tdrop
        pkgs.tmux
      ];

      files = {
        ".tmux.conf" = ./terminals/tmux.conf;
        ".config/guake/guake.con" = ./terminals/config/guake/guake.conf;
        ".config/alacritty/alacritty.yml" = ./terminals/config/alacritty/alacritty.yml;
      };
    };

    vim = {
      files = {
        # ".vimrc" = ./vim/vimrc;
        ".vim/coc-settings.json" = ./vim/vim/vim-coc-settings.json;
      };
      packages = [ pkgs.rnix-lsp ];
    };

    wallpaper = { packages = [ pkgs.variety pkgs.nitrogen ]; };
  });

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


  # ----------------------------------------------------------------------------

  importModule = 
    let args = {
      inherit config pkgs lib;
    }; in path: (import path args);
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

  ##
  ## Managed configs
  ##

  fonts.fontconfig.enable = true;

  programs = {
    # Let Home Manager install and manage itself.
    home-manager.enable = true;

    # # Rofi (drun-style launcher)
    # rofi = {
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

    fish = importModule fish/fish.nix;

    # Newsboat (RSS feed reader)
    newsboat = importModule newsboat/newsboat.nix;

    vim = importModule vim/vim.nix;

    # Nix-related tools
    direnv = {
      enable = true;
      nix-direnv.enable = true;
    };
  };


  ##
  ## Unmanaged configs
  ##
  home.file = unManagedConfigs.files;
  home.packages = unManagedConfigs.packages;
}
