{ lib, pkgs, ... }:
  let
    common = import ./common.nix { inherit lib pkgs; };

    convertBool = name: value: if value then "set " + name else "set no" + name;

    convertSetting = name: value:
      if builtins.isList value then
        "set " + name + "=" + (lib.concatStringsSep "," value)
      else if builtins.isInt value || builtins.isString value then
        "set " + name + "=" + builtins.toString value
      else if builtins.isBool value then
        convertBool name value
      else
        throw "Unsupported setting type for ${name}";

    vimscriptFromSettings = settings:
      lib.concatStringsSep "\n" (lib.mapAttrsToList convertSetting settings);

    vimSettings = vimscriptFromSettings common.settings;

    # Neovim-only plugins
    aiken-integration = pkgs.vimUtils.buildVimPlugin {
      name = "editor-integration-nvim";
      src = pkgs.fetchFromGitHub {
        owner = "aiken-lang";
        repo = "editor-integration-nvim";
        rev = "a816a1f171a5d53c9e5dcba6f6823f5d5e51d559";
        sha256 = "v6/6oAPOgvMHpULDSyN1KzOf33q92Wri2BcqcuHGJzI=";
      };
    };

    neovimExtraPlugins = with pkgs.vimPlugins; [
      nvim-lspconfig
      blink-cmp
      friendly-snippets
      lean-nvim
      aiken-integration
      zen-mode-nvim
      gitsigns-nvim
      diffview-nvim
    ];

    neovimPlugins = common.plugins ++ neovimExtraPlugins;

    luaLspConfig = ''
      lua << EOF
      local blink_ok, blink = pcall(require, 'blink.cmp')
      if blink_ok then
        blink.setup({})
      end

      local lspconfig_ok, lspconfig = pcall(require, 'lspconfig')
      if lspconfig_ok then
        local capabilities = vim.lsp.protocol.make_client_capabilities()
        if blink_ok and blink.get_lsp_capabilities then
          capabilities = vim.tbl_deep_extend('force', capabilities, blink.get_lsp_capabilities())
        end

        local function on_attach(_, bufnr)
          local function map(lhs, rhs)
            vim.keymap.set('n', lhs, rhs, { buffer = bufnr, silent = true })
          end
          map('gh', vim.lsp.buf.hover)
          map('ga', vim.lsp.buf.code_action)
          map('ge', vim.diagnostic.open_float)
          map('gd', vim.lsp.buf.definition)
          map('gr', vim.lsp.buf.references)
        end

        local servers = { 'rust_analyzer', 'ts_ls', 'nil_ls', 'aiken', 'pyright' }
        for _, server in ipairs(servers) do
          if lspconfig[server] then
            lspconfig[server].setup({
              capabilities = capabilities,
              on_attach = on_attach,
            })
          end
        end
      end

      -- Global fallbacks so mappings work even before LSP attaches
      vim.keymap.set('n', 'gh', function()
        if vim.lsp.buf.hover then vim.lsp.buf.hover() end
      end, { silent = true })
      vim.keymap.set('n', 'ga', function()
        if vim.lsp.buf.code_action then vim.lsp.buf.code_action() end
      end, { silent = true })
      vim.keymap.set('n', 'gd', function()
        if vim.lsp.buf.definition then vim.lsp.buf.definition() end
      end, { silent = true })
      vim.keymap.set('n', 'gr', function()
        if vim.lsp.buf.references then vim.lsp.buf.references() end
      end, { silent = true })
      vim.diagnostic.config({
        virtual_text = true,
      })
      EOF
    '';
  in {
    enable = true;
    plugins = neovimPlugins;
    extraConfig = vimSettings + "\n" + common.extraConfig + "\n" + luaLspConfig;
  }
