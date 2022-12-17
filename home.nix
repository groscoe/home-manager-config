{ config, pkgs, lib, ... }:

let
  # Configs go here. Don't forget to add to `unManagedConfigs`;
  unManagedConfigs = build (lib.attrValues {
    bash = {
      files = {
        ".bashrc" = ./bashrc;
        ".bash_aliases" = ./bash_aliases;
        ".fzf.bash" = ./bash-fzf.bash;
      };
    };

    deluge = { packages = [ pkgs.deluge ]; };

    fzf = { packages = [ pkgs.fzf pkgs.fd ]; };

    git = {
      files = {
        ".gitconfig" = ./gitconfig;
        ".git_aliases.sh" = ./git_aliases.sh;
      };

      packages = [ pkgs.diff-so-fancy ];
    };

    haskell = { files = { ".ghc/ghci.conf" = ./haskell-ghci.conf; }; };

    i3 = { files = { ".config/i3/config" = ./i3-config; }; };

    logseq = { packages = [ pkgs.logseq ]; };

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

    notifications = {
      files = {
        ".config/deadd/deadd.conf" = ./deadd.conf;
        ".config/deadd/deadd.css" = ./deadd.css;
      };
    };

    picom = { files = { ".config/picom/picom.conf" = ./picom.conf; }; };

    # polybar = {
    #   # NOTE: weird inconsistencies.
    #   packages = [ pkgs.polybar ];

    #   files = { ".config/polybar/config" = ./polybar; };
    # };

    programming-tools = { packages = [ pkgs.comby pkgs.pretty-simple ]; };

    ripgrep = {
      files = { ".ripgreprc" = ./ripgreprc; };
      packages = [ pkgs.ripgrep ];
    };

    rofi = {
      # NOTE: Managed version doesn't find .desktop files that weren't installed
      # with nix.
      files = {
        ".config/rofi/config.rasi" = ./rofi.rasi;
        ".config/rofi/file-browser" = ./rofi-file-browser;
      };
    };

    terminals = {
      packages = [
        # pkgs.alacritty # NOTE: GPU acceleration issues
        pkgs.tdrop
      ];

      files = {
        ".tmux.conf" = ./tmux.conf;
        ".config/guake/guake.con" = ./guake.conf;
        ".config/alacritty/alacritty.yml" = ./alacritty.yml;
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

  programs.fish = {
    enable = true;

    plugins = [
      {
        name = "foreign-env";
        src = pkgs.fetchFromGitHub {
          owner = "oh-my-fish";
          repo = "plugin-foreign-env";
          rev = "master";
          sha256 = "sha256-3h03WQrBZmTXZLkQh1oVyhv6zlyYsSDS7HTHr+7WjY8=";
        };
      }

      {
        name = "bass";
        src = pkgs.fetchFromGitHub {
          owner = "edc";
          repo = "bass";
          rev = "master";
          sha256 = "sha256-fl4/Pgtkojk5AE52wpGDnuLajQxHoVqyphE90IIPYFU=";
        };
      }
    ];

    shellInit = ''
      # Common variables
      set -x PATH \
      	$HOME/.cargo/bin \
      	$HOME/.npm-packages/bin \
      	$HOME/.local/bin \
      	$HOME/.cabal/bin \
      	$PATH

      set -x EDITOR vim

      # Nix
      fenv source $HOME/.nix-profile/etc/profile.d/nix.sh
      set -x LOCALE_ARCHIVE /usr/lib/locale/locale-archive
      source (direnv hook fish | psub)
    '';

    interactiveShellInit = ''
      # My custom, decade-old, function definitions
      bass source ~/.bash_aliases

      # FZF integration
      set -x RIPGREP_CONFIG_PATH $HOME/.ripgreprc
      set -x FZF_FIND_FILE_OPTS "--layout=reverse --bind='ctrl-t:toggle-preview' --preview='/home/groscoe/Projects/preview.sh {}' --height=100%"
      set -x FZF_FIND_FILE_COMMAND "fd -L -H"
    '';

    functions = {
      fish_right_prompt = ''
        if test $CMD_DURATION
            # Show duration of the last command in seconds
            set duration (echo "$CMD_DURATION 1000" | awk '{printf "%.3fs", $1 / $2}')
            echo $duration
        end
      '';

      fish_user_key_bindings = "fzf_key_bindings";
    };
  };

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

  ##
  ## Unmanaged configs
  ##
  home.file = unManagedConfigs.files;
  home.packages = unManagedConfigs.packages;
}
