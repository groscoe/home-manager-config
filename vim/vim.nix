{ pkgs, ... }:
{
  enable = true;

  plugins = with pkgs.vimPlugins;
  let
    aiken-integration = pkgs.vimUtils.buildVimPlugin {
      name = "editor-integration-nvim";
      src = pkgs.fetchFromGitHub {
        owner = "aiken-lang";
        repo = "editor-integration-nvim";
        rev = "a816a1f171a5d53c9e5dcba6f6823f5d5e51d559";
        sha256 = "v6/6oAPOgvMHpULDSyN1KzOf33q92Wri2BcqcuHGJzI=";
      };
    };
  in [
    aiken-integration
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

    # Lean4 support
    lean-nvim
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

    mouse = "a";
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
    set background=light

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

    " Add a space after commenting with NERDCommenter
    let g:NERDSpaceDelims = 1

    " Highlight trailing spaces
    highlight TrailingSpace ctermbg=red guibg=red
    autocmd BufRead,BufNewFile * match TrailingSpace /\s\+$/


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

    " command-line history
    cnoremap <C-r><C-r> <C-u>History:<CR>

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
}
