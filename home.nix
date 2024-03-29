{ config, pkgs, lib, pkgs-stable, ... }:

let
  # Configs go here.
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

    # doom-emacs = {
      # packages = [ doom-emacs ];
    # };

    fzf = { packages = [ pkgs.fzf pkgs.fd ]; };

    finance = {
      packages = with pkgs; [
        gnucash
        hledger-ui
        hledger-web
      ];
    };

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

    hledger = { packages = [ pkgs.hledger ]; };

    logseq = { packages = [ pkgs.logseq ]; };

    media = {
      packages = [ pkgs.vlc ];
    };

    networking-tools = {
      packages = [ pkgs.lsof pkgs.speedtest-cli pkgs.nethogs ];
    };

    nix-tools = {
      packages = with pkgs; [
        nixfmt # formatter
        cntr # container debugging tool
        cachix # binary caches
        direnv
        nix-output-monitor
        nil
      ];
    };

    peripherics-tools = {
      packages = with pkgs; [
        brightnessctl
        pavucontrol
        playerctl
      ];
    };

    ebook-utilities = {
      packages = with pkgs; [
        poppler_utils
        calibre
      ];
    };

    picom = { files = { ".config/picom/picom.conf" = ./picom/config/picom/picom.conf; }; };

    polybar = {
      # NOTE: weird inconsistencies.
      # packages = [ pkgs.polybar ];

      files = { ".config/polybar" = ./polybar/config/polybar; };
    };

    programming-tools = {
      packages = with pkgs; [
        cloc
        cmake
        comby
        nodejs
        pkgs-stable.httpie
        pretty-simple
        pup
        shellcheck
        visidata

        (google-cloud-sdk.withExtraComponents [google-cloud-sdk.components.gke-gcloud-auth-plugin])

        ] ++ (with pkgs.nodePackages; [
          graphql-language-service-cli
        ]);
      };

    ripgrep = {
      files = { ".ripgreprc" = ./ripgrep/ripgreprc; };
      packages = [ pkgs.ripgrep ];
    };

    rofi = {
      # NOTE: Managed version doesn't find .desktop files that weren't installed
      # with nix.
      files = {
        # ".config/rofi/config.rasi" = ./rofi/config/rofi/rofi.rasi;
        ".config/rofi/file-browser" = ./rofi/config/rofi/rofi-file-browser;
      };
    };

    shell-utilities = {
      packages = with pkgs; [
        bat
        gcal
        gotop
        gron
        jq
        lsd
        parallel
        rclone
        tree
        xclip
      ];
    };

    # spacemacs = {
    #   files = {
    #     ".spacemacs" = ./spacemacs/spacemacs.el;
    #     ".emacs.d" = {
    #       source = builtins.fetchGit {
    #         url = "https://github.com/syl20bnr/spacemacs";
    #         ref = "develop";
    #       };
    #       # don't make the directory read only so that impure melpa can still
    #       # happen.
    #       recursive = true;
    #     };
    #   };
    # };

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

  manual.manpages.enable = false;

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

    # Rofi (drun-style launcher)
    rofi = importModule rofi/rofi.nix;

    fish = importModule fish/fish.nix;

    # Newsboat (RSS feed reader)
    newsboat = importModule newsboat/newsboat.nix;

    vim = importModule vim/vim.nix;
    neovim = importModule vim/nvim.nix;

    # Nix-related tools
    direnv = {
      enable = true;
      nix-direnv.enable = true;
    };

    # # emacs
    # emacs = {
    #   enable = true;
    #   package = pkgs.emacsWithPackages (epkgs: with epkgs; [
    #     zerodark-theme
    #   ]);
    #   extraPackages = epkgs: with epkgs; [
    #     zerodark-theme
    #     magit
    #     org-download
    #   ];
    # };

    zathura = {
      enable = true;

      mappings = {
        h = "navigate previous";
        l = "navigate next";
      };

      options = {
        # zathurarc-dark
        notification-error-bg = "#586e75"; # base01  # seem not work
        notification-error-fg = "#dc322f"; # red
        notification-warning-bg = "#586e75"; # base01
        notification-warning-fg = "#dc322f"; # red
        notification-bg = "#586e75"; # base01
        notification-fg = "#b58900"; # yellow

        completion-group-bg = "#002b36"; # base03
        completion-group-fg = "#839496"; # base0
        completion-bg = "#073642"; # base02
        completion-fg = "#93a1a1"; # base1
        completion-highlight-bg = "#586e75"; # base01
        completion-highlight-fg = "#eee8d5"; # base2

        # Define the color in index mode
        index-bg = "#073642"; # base02
        index-fg = "#93a1a1"; # base1
        index-active-bg = "#586e75"; # base01
        index-active-fg = "#eee8d5"; # base2

        inputbar-bg = "#586e75"; # base01
        inputbar-fg = "#eee8d5"; # base2

        statusbar-bg = "#073642"; # base02
        statusbar-fg = "#93a1a1"; # base1

        highlight-color = "#657b83"; # base00  # hightlight match when search keyword(vim's /)
        highlight-active-color = "#268bd2"; # blue

        # default-bg = "#073642"; # base02
        default-bg = "#000000"; # base02
        default-fg = "#93a1a1"; # base1
        # render-loading = true
        # render-loading-fg = "#073642"; # base02
        # render-loading-bg = "#073642"; # base02

        # Recolor book content's color
        # recolor = true;
        recolor-lightcolor = "#073642"; # base02
        recolor-darkcolor = "#93a1a1"; # base1
        # recolor-keephue = true      # keep original color
      };
    };
  };

  ##
  ## Unmanaged configs
  ##
  home.file = unManagedConfigs.files;
  home.packages = unManagedConfigs.packages;
}
