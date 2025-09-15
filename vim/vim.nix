{ pkgs, lib, ... }:
let
  common = import ./common.nix { inherit lib pkgs; };
in {
  enable = true;

  plugins = with pkgs.vimPlugins;
    common.plugins ++ [
      # Auto-complete/intellisense (Vim-only)
      coc-nvim
      coc-rust-analyzer
      coc-tsserver
    ];

  settings = common.settings;

  extraConfig = common.extraConfig + ''
    ""
    "" CoC-specific mappings (Vim)
    ""

    " From https://github.com/neoclide/coc.nvim#example-vim-configuration
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
  '';
}
