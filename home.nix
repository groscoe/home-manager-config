{ config, pkgs, lib, ... }:

let
  # Configs go here. Don't forget to add to `unManagedConfigs`;
  unManagedConfigs = build (lib.attrValues {
    acpi = { packages = [ pkgs.acpi ]; };

    bash = {
      files = {
        ".bashrc" = ./bashrc;
        ".bash_aliases" = ./bash_aliases;
        ".fzf.bash" = ./bash-fzf.bash;
      };
    };


    deluge = { packages = [ pkgs.deluge ]; };

    fzf = { packages = [ pkgs.fzf pkgs.fd ]; };

    fonts = { packages = [ pkgs.source-code-pro ]; };

    git = {
      files = {
        ".gitconfig" = ./gitconfig;
        ".git_aliases.sh" = ./git_aliases.sh;
      };

      packages = [ pkgs.diff-so-fancy ];
    };

    haskell = { files = { ".ghc/ghci.conf" = ./haskell-ghci.conf; }; };

    i3 = {
      packages = [ pkgs.i3-gaps ];
      files = { ".config/i3/config" = ./i3-config; };
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

    notifications = {
      files = {
        ".config/deadd/deadd.conf" = ./deadd.conf;
        ".config/deadd/deadd.css" = ./deadd.css;
      };
    };

    picom = { files = { ".config/picom/picom.conf" = ./picom.conf; }; };

    polybar = {
      # NOTE: weird inconsistencies.
      # packages = [ pkgs.polybar ];

      files = { ".config/polybar" = ./polybar; };
    };

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
        ".tmux.conf" = ./tmux.conf;
        ".config/guake/guake.con" = ./guake.conf;
        ".config/alacritty/alacritty.yml" = ./alacritty.yml;
      };
    };

    vim = {
      files = {
        # ".vimrc" = ./vimrc;
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

  fonts.fontconfig.enable = true;

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

  programs.vim = {
    enable = true;

    plugins = with pkgs.vimPlugins; [
      # Easier handling of delimiters
      vim-surround

      # Auto-complete/intellisense
      coc-nvim
      coc-rust-analyzer

      # Better syntax highlighting
      vim-polyglot

      # Search with fzf
      fzf-vim

      # Improvements on netrw, see https://github.com/tpop/vim-vinegar
      vim-vinegar

      # Smart commenting plugin
      nerdcommenter

      ##
      ## Nice colorschemes
      ##

      # For dark backgrounds
      onehalf

      # Dynamic colorscheme with pywal
      wal-vim

      # Solarized
      vim-colors-solarized

      # Nord theme
      nord-vim
    ];

    settings = {
      # From https://stackoverflow.com/questions/234564/tab-key-4-spaces-and-auto-indent-after-curly-braces-in-vim
      tabstop = 2;
      shiftwidth = 2;
      expandtab = true;

      # From https://jeffkreeftmeijer.com/vim-number/
      number = true;
      relativenumber = true;

      # From https://stackoverflow.com/a/2288438
      ignorecase = true;
      smartcase = true;

      # Persistent history
      undodir = [ "~/.vimhistory" ];
      undofile = true;

      # Hide buffers in other windows, don't destroy them
      hidden = true;

      background = "light";
    };

    extraConfig = ''
      ""
      "" SetCompletionMappings()
      ""

      " From https://github.com/neoclide/coc.nvim#example-vim-configuration
      " Use K to show documentation in preview window.
      nnoremap <silent> gh :call <SID>show_documentation()<CR>
      nnoremap <silent> ga <Plug>(coc-codeaction)
      nnoremap <silent> gd :call CocActionAsync('jumpDefinition')<CR>
      nnoremap <silent> gr <Plug>(coc-references)

      function! s:show_documentation()
        if (index(['vim','help'], &filetype) >= 0)
          execute 'h '.expand('<cword>')
        elseif (coc#rpc#ready())
          call CocActionAsync('doHover')
        else
          execute '!' . &keywordprg . " " . expand('<cword>')
        endif
      endfunction  

      ""
      "" SetupVisuals()
      ""

      " From https://github.com/sonph/onehalf/tree/master/vim#true-colors
      " if exists('+termguicolors')
      "   let &t_8f = "\<Esc>[38;2;%lu;%lu;%lum"
      "   let &t_8b = "\<Esc>[48;2;%lu;%lu;%lum"
      "   set termguicolors
      " endif

      syntax enable
      " let g:solarized_termcolors=256
      " let g:solarized_termtrans=1
      colorscheme nord
      " set background=light

      ""
      "" SetupEditor()
      ""

      " When opening a file, change the current working dir
      set autochdir

      " Persistent history
      " set undodir=~/.vimhistory
      " set undofile

      " Hide buffers in other windows, don't destroy them
      " set hidden

      " Close buffer with C-w
      " nnoremap <silent> <C-x> :bw<CR>

      " Some handy buffer navigation shortcuts
      nnoremap <silent> <C-n> :bn<CR>
      nnoremap <silent> <C-p> :bp<CR>


      ""
      "" SetupFZFBindings()
      ""

      " From https://dev.to/iggredible/how-to-search-faster-in-vim-with-fzf-vim-36ko
      nnoremap <silent> <C-t> :GFiles<CR>
      nnoremap <silent> <C-b> :Buffers<CR>

      command! -bang -nargs=* GGrep
        \ call fzf#vim#grep(
        \   'git grep --line-number -- '.shellescape(<q-args>), 0,
        \   fzf#vim#with_preview({'dir': systemlist('git rev-parse --show-toplevel')[0]}), <bang>0)

      nnoremap <silent> <C-h> :GGrep<CR>

      ""
      "" SetupSpellChecking()
      ""
      augroup textWithSpellCheck
        autocmd!
        autocmd FileType latex,tex,md,rst,markdown,org,txt setlocal spell spelllang=en_gb
        autocmd BufRead,BufNewFile *.md,*.org,*.txt setlocal spell spelllang=en_gb
      augroup END



      ""
      "" HighlightTODOs()
      ""

      " Highlight TODO, FIXME, etc for every filetype
      augroup higlightTODO
        autocmd!
        autocmd WinEnter,VimEnter * :silent! call matchadd('Todo', 'NOTE\|NB\|REVIEW\|TMP', -1)
      augroup END

      " call SetupVisuals()
      " call SetCompletionMappings()
      " call SetupSpellChecking()
      " call SetupEditor()
      " call SetupFZFBindings()
      " call HighlightTODOs()
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
