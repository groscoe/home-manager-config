function! InitializePlug()
  " Bootstrapping vim-plug
  call plug#begin('~/.vim/plugged')
endfunction

function! DefinePlugins()
  call InitializePlug()

  " Plug plugins go here

  " Easier handling of delimiters 
  Plug 'tpope/vim-surround'

  " Auto-complete/intellisense
  Plug 'neoclide/coc.nvim', {'branch': 'release'}

  " Better syntax highlighting
  Plug 'sheerun/vim-polyglot'

  " Nice color scheme for dark backgrounds
  Plug 'sonph/onehalf', {'rtp': 'vim'}

  " Another nice color scheme
  Plug 'altercation/vim-colors-solarized'

  " Search with fzf
  Plug 'junegunn/fzf', { 'do': { -> fzf#install() } }
  Plug 'junegunn/fzf.vim'

  " Improvements on netrw, see https://github.com/tpope/vim-vinegar
  Plug 'tpope/vim-vinegar'

  " Smart commenting plugin
  Plug 'preservim/nerdcommenter'

  call plug#end()
endfunction


" From https://stackoverflow.com/questions/234564/tab-key-4-spaces-and-auto-indent-after-curly-braces-in-vim
function! ConfigIndentation()
  filetype plugin indent on
  " show existing tab with 4 spaces width
  set tabstop=2
  " when indenting with '>', use 4 spaces width
  set shiftwidth=2
  " On pressing tab, insert 4 spaces
  set expandtab 
endfunction


" From https://jeffkreeftmeijer.com/vim-number/
function! ConfigLineNumbers()
  set number relativenumber
  set nu rnu
endfunction

" From https://stackoverflow.com/a/2288438
function! ConfigSmartCasedSearch()
  set ignorecase
  set smartcase
endfunction


" From https://github.com/neoclide/coc.nvim#example-vim-configuration
function! SetCompletionMappings()
	" Use K to show documentation in preview window.
	nnoremap <silent> gh :call <SID>show_documentation()<CR>
  nnoremap <silent> ga :CocAction<CR>
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
endfunction

function! SetupVisuals()
  " From https://github.com/sonph/onehalf/tree/master/vim#true-colors
  " if exists('+termguicolors')
  "   let &t_8f = "\<Esc>[38;2;%lu;%lu;%lum"
  "   let &t_8b = "\<Esc>[48;2;%lu;%lu;%lum"
  "   set termguicolors
  " endif

  syntax enable
  set background=dark
  " let g:solarized_termcolors=256
  let g:solarized_termtrans=1
  colorscheme solarized
endfunction

function! SetupEditor()
  " When opening a file, change the current working dir
  set autochdir

  " Persistent history
  set undodir=~/.vimhistory
  set undofile

  " Hide buffers in other windows, don't destroy them
  set hidden

  " Close buffer with C-w
  " nnoremap <silent> <C-x> :bw<CR>

  " Some handy buffer navigation shortcuts
  nnoremap <silent> <C-w> :bw<CR>
  nnoremap <silent> <C-n> :bn<CR>
  nnoremap <silent> <C-p> :bp<CR>
endfunction

" From https://dev.to/iggredible/how-to-search-faster-in-vim-with-fzf-vim-36ko
function! SetupFZFBindings()
  nnoremap <silent> <C-t> :GFiles<CR>
  nnoremap <silent> <C-b> :Buffers<CR>

	command! -bang -nargs=* GGrep
		\ call fzf#vim#grep(
		\   'git grep --line-number -- '.shellescape(<q-args>), 0,
		\   fzf#vim#with_preview({'dir': systemlist('git rev-parse --show-toplevel')[0]}), <bang>0)

  nnoremap <silent> <C-h> :GGrep<CR>
endfunction

function! SetupSpellChecking()
  augroup textWithSpellCheck
    autocmd!
    autocmd FileType latex,tex,md,rst,markdown,org,txt setlocal spell spelllang=en_gb
    autocmd BufRead,BufNewFile *.md,*.org,*.txt setlocal spell spelllang=en_gb
  augroup END
endfunction

" Highlight TODO, FIXME, etc for every filetype
function! HighlightTODOs()
  augroup higlightTODO
    autocmd!
    autocmd WinEnter,VimEnter * :silent! call matchadd('Todo', 'NOTE\|NB\|REVIEW\|TMP', -1)
  augroup END
endfunction

call DefinePlugins()
call SetupVisuals()
call ConfigIndentation()
call ConfigLineNumbers()
call ConfigSmartCasedSearch()
call SetCompletionMappings()
call SetupSpellChecking()
call SetupEditor()
call SetupFZFBindings()
call HighlightTODOs()

