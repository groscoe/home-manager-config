args@{ lib, pkgs, ... }:
{
  plugins = with pkgs.vimPlugins; [
    # Cross-compat plugins
    vim-surround
    vim-polyglot
    fzf-vim
    vim-vinegar
    nerdcommenter

    # Colorschemes
    onehalf
    wal-vim
    vim-colors-solarized
    nord-vim
  ];

  settings = {
    # Indentation
    tabstop = 2;
    shiftwidth = 2;
    expandtab = true;

    # Line numbers
    number = true;
    relativenumber = true;

    # Search
    ignorecase = true;
    smartcase = true;

    # Persistent undo
    undodir = [ "~/.local/state/vim/undo" ];
    undofile = true;

    # Buffer handling
    hidden = true;

    # Visuals
    background = "dark";
    mouse = "a";
  };

  extraConfig = ''
    ""
    "" Shared visuals and editor behavior
    ""

    syntax enable
    colorscheme nord
    set termguicolors

    " Keep language syntax colors visible inside diff hunks.
    function! s:diff_syntax_foreground() abort
      " Preserve syntax foreground, but enforce high-contrast diff backgrounds.
      highlight DiffAdd cterm=NONE gui=NONE ctermfg=NONE ctermbg=22 guifg=NONE guibg=#1f3d2b
      highlight DiffDelete cterm=NONE gui=NONE ctermfg=NONE ctermbg=52 guifg=NONE guibg=#4a1f24
      highlight DiffChange cterm=NONE gui=NONE ctermfg=NONE ctermbg=17 guifg=NONE guibg=#22324f
      highlight DiffText cterm=bold gui=bold ctermfg=NONE ctermbg=24 guifg=NONE guibg=#2f4f7a
    endfunction

    augroup DiffSyntaxForeground
      autocmd!
      autocmd ColorScheme * call s:diff_syntax_foreground()
    augroup END
    call s:diff_syntax_foreground()

    " When opening a file, change the current working dir
    set autochdir

    " Some handy buffer navigation shortcuts
    nnoremap <silent> <C-n> :bn<CR>
    nnoremap <silent> <C-p> :bp<CR>

    " Use space as leader in both Vim and Neovim
    let mapleader = " "
    let maplocalleader = " "

    " Add a space after commenting with NERDCommenter
    let g:NERDSpaceDelims = 1

    " Highlight trailing spaces
    highlight TrailingSpace ctermbg=red guibg=red
    autocmd BufRead,BufNewFile * match TrailingSpace /\s\+$/

    ""
    "" FZF: files, buffers, ripgrep wrapper
    ""
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
    "" Spell checking defaults
    ""
    augroup textWithSpellCheck
      autocmd!
      autocmd FileType latex,tex,md,rst,markdown,org,txt setlocal spell spelllang=en_gb
      autocmd BufRead,BufNewFile *.md,*.org,*.txt setlocal spell spelllang=en_gb
    augroup END

    ""
    "" Highlight TODO, FIXME, etc for every filetype
    ""
    augroup higlightTODO
      autocmd!
      autocmd WinEnter,VimEnter * :silent! call matchadd('Todo', 'NOTE\|NB\|REVIEW\|TMP', -1)
    augroup END
  '';
}
