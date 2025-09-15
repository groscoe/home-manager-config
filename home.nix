{ config, pkgs, lib, pkgs-stable, ... }:

let
  isDarwin = pkgs.stdenv.isDarwin;
  ifDarwin = cfg:
    let empty = if builtins.isAttrs cfg then {} else [];
    in if isDarwin then cfg else empty;
  ifNotDarwin = cfg:
    let empty = if builtins.isAttrs cfg then {} else [];
    in if isDarwin then empty else cfg;
  # Configs go here.
  unManagedConfigs = build (lib.attrValues {
    acpi = ifNotDarwin { packages = [ pkgs.acpi ]; };

    bash = {
      files = {
        ".bashrc" = ./bash/bashrc;
        ".bash_aliases" = ./bash/bash_aliases;
        ".fzf.bash" = ./bash/fzf.bash;
      };
    };

    backup-tools = {
      packages = with pkgs; [
        restic
        rclone
      ];
    };

    # Notifications
    deadd = ifNotDarwin {
      packages = [ ];
      files = {
        ".config/deadd/deadd.conf" = ./deadd/config/deadd/deadd.conf;
        ".config/deadd/deadd.css" = ./deadd/config/deadd/deadd.css;
      };
    };

    deluge = { packages = [ pkgs.deluge ]; };

    # doom-emacs = {
      # packages = [ doom-emacs ];
    # };

    fzf = { packages = [ pkgs.fzf ]; };

    finance = {
      packages = with pkgs; [
        hledger-ui
        hledger-web
      ] ++ ifNotDarwin [ pkgs.gnucash ];
    };

    fonts = {
      packages = with pkgs; [
        source-code-pro
      ] ++ (
        # Install all subpackages from nerd-fonts
        builtins.filter lib.attrsets.isDerivation (builtins.attrValues nerd-fonts)
      );
    };

    git = {
      files = {
        ".gitconfig" = ./git/gitconfig;
        ".git_aliases.sh" = ./git/git_aliases.sh;
      };

      packages = with pkgs; [
        diff-so-fancy
        delta
      ];
    };

    haskell = {
      files = {
        ".ghc/ghci.conf" = ./haskell/ghc/ghci.conf;
        ".haskeline" = ./haskell/ghc/haskeline;
      };
    };

    # kmonad = ifNotDarwin {
    #   packages = [ pkgs.kmonad ];
    # };

    i3 = ifNotDarwin {
      packages = [ pkgs.i3-gaps ];
      files = { ".config/i3/config" = ./i3/config/i3/config; };
    };

    hledger = { packages = [ pkgs.hledger ]; };

    media = ifNotDarwin {
      packages = [ pkgs.vlc ];
    };

    networking-tools = {
      packages = with pkgs; [
        lsof
        speedtest-cli
        wireshark
      ] ++ ifNotDarwin [ pkgs.nethogs ];

      activationScripts = {
        wireshark = lib.hm.dag.entryAfter ["writeBoundry"] ''
          $DRY_RUN_CMD [ -f ~/Applications/Wireshark.app ] && rm -rf ~/Applications/Wireshark.app
          $DRY_RUN_CMD cp -r ${pkgs.wireshark}/Applications/Wireshark.app ~/Applications
          $DRY_RUN_CMD chmod -R 755 ~/Applications/Wireshark.app
        '';
      };
    };

    nix-tools = {
      packages = with pkgs; [
        nixfmt-rfc-style # formatter
        cachix # binary caches
        direnv
        nix-output-monitor
        nil
        nix-search
      ] ++ ifNotDarwin [ pkgs.cntr ];
    };

    peripherics-tools = ifNotDarwin {
      packages = with pkgs; [
        brightnessctl
        blueman
        pavucontrol
        playerctl
        xcape
      ];
    };

    ebook-utilities = {
      packages = with pkgs; [
        xournalpp
        poppler_utils
      ] ++ ifNotDarwin [ pkgs.calibre ];
    };

    picom = ifNotDarwin { files = { ".config/picom/picom.conf" = ./picom/config/picom/picom.conf; }; };

    polybar = ifNotDarwin {
      # NOTE: weird inconsistencies.
      # packages = [ pkgs.polybar ];

      files = { ".config/polybar" = ./polybar/config/polybar; };
    };

    programming-tools = {
      packages = with pkgs; [
        cloc
        cmake
        nodejs
        rust-analyzer
        typescript-language-server
        # pkgs-stable.httpie
        pretty-simple
        pup
        shellcheck
        visidata
        spek

        (google-cloud-sdk.withExtraComponents [google-cloud-sdk.components.gke-gcloud-auth-plugin])

        ];
        # ] ++ (with pkgs.nodePackages; [
          # graphql-language-service-cli
        # ]);
      };

    ripgrep = {
      files = { ".ripgreprc" = ./ripgrep/ripgreprc; };
      packages = [ pkgs.ripgrep ];
    };

    rofi = ifNotDarwin {
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
        gnupg
        gron
        jq
        lsd
        parallel
        rclone
        tree
        xclip
        xsel
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
      packages = with pkgs; [
        # alacritty # NOTE: GPU acceleration issues
        tmux
        mosh
      ] ++ ifNotDarwin [ pkgs.tdrop ];

      files = {
        ".tmux" = ./terminals/tmux;
        ".tmux.conf" = ./terminals/tmux.conf;
        ".config/guake/guake.conf" = ./terminals/config/guake/guake.conf;
        ".config/alacritty/alacritty.toml" = ./terminals/config/alacritty/alacritty.toml;
      };
    };

    vim = {
      files = {
        ".vim/coc-settings.json" = ./vim/vim/vim-coc-settings.json;
      };
    };

    wallpaper = ifNotDarwin {
      packages = with pkgs; [
        feh
        nitrogen
        variety
      ];
    };

    macos = ifDarwin {
      packages = [ pkgs.iterm2 ];
    };

    copyNixApps = ifDarwin {
      activationScripts = {
        copyNixApps = lib.hm.dag.entryAfter ["linkGeneration"] ''
          # Create directory for the applications
          mkdir -p "$HOME/Applications/Nix-Apps"
          # Remove old entries
          rm -rf "$HOME/Applications/Nix-Apps"/*
          # Get the target of the symlink
          NIXAPPS=$(readlink -f "$HOME/.nix-profile/Applications")
          # For each application
          for app_source in "$NIXAPPS"/*; do
            if [ -d "$app_source" ] || [ -L "$app_source" ]; then
                appname=$(basename "$app_source")
                target="$HOME/Applications/Nix-Apps/$appname"

                # Create the basic structure
                mkdir -p "$target"
                mkdir -p "$target/Contents"

                # Copy the Info.plist file
                if [ -f "$app_source/Contents/Info.plist" ]; then
                  mkdir -p "$target/Contents"
                  cp -f "$app_source/Contents/Info.plist" "$target/Contents/"
                fi

                # Copy icon files
                if [ -d "$app_source/Contents/Resources" ]; then
                  mkdir -p "$target/Contents/Resources"
                  find "$app_source/Contents/Resources" -name "*.icns" -exec cp -f {} "$target/Contents/Resources/" \;
                fi

                # Symlink the MacOS directory (contains the actual binary)
                if [ -d "$app_source/Contents/MacOS" ]; then
                  ln -sfn "$app_source/Contents/MacOS" "$target/Contents/MacOS"
                fi

                # Symlink other directories
                for dir in "$app_source/Contents"/*; do
                  dirname=$(basename "$dir")
                  if [ "$dirname" != "Info.plist" ] && [ "$dirname" != "Resources" ] && [ "$dirname" != "MacOS" ]; then
                    ln -sfn "$dir" "$target/Contents/$dirname"
                  fi
                done
            fi
          done
      '';
      };
    };
  });

  # ----------------------------------------------------------------------------

  toSources = builtins.mapAttrs
    (_: file: if builtins.isAttrs file then file else { source = file; });

  # Merge all configs together
  build = configs:
    builtins.foldl' (acc:
      { files ? { }, packages ? [ ], activationScripts ? { }, ... }: {
        files = acc.files // toSources files;
        packages = acc.packages ++ packages;
        activationScripts = acc.activationScripts // activationScripts;
      }) {
        files = { };
        packages = [ ];
        activationScripts = { };
      } configs;


  # ----------------------------------------------------------------------------

  importModule =
    let args = {
      inherit config pkgs lib isDarwin;
    }; in path: (import path args);
  
  username = "groscoe";
in {
  # Home Manager needs a bit of information about you and the
  # paths it should manage.
  home.username = username;
  home.homeDirectory = if isDarwin then "/Users/${username}" else "/home/${username}";

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

    # Smarter shell history search
    atuin = {
      enable = true;
      enableFishIntegration = true;
      enableBashIntegration = true;

      settings = {
        dialect = "uk";
        style = "compact";
        secrets_filter = "false";
      };
    };

    # Newsboat (RSS feed reader)
    newsboat = importModule newsboat/newsboat.nix;

    vim = importModule vim/vim.nix;
    neovim = importModule vim/nvim.nix;

    # Nix-related tools
    direnv = {
      enable = true;
      nix-direnv.enable = true;
    };

    # emacs
    emacs = ifNotDarwin {
      enable = true;
      package = pkgs.emacs.pkgs.withPackages (epkgs: with epkgs; [
        zerodark-theme
      ]);
      extraPackages = epkgs: with epkgs; [
        zerodark-theme
        magit
        org-download
      ];
    };

    # fd - an alternative to `find`
    fd = {
      enable = true;
    };

    zathura = {
      enable = true;

      package = pkgs.zathuraPkgs.zathuraWrapper;

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
  home.activation = unManagedConfigs.activationScripts;
}
