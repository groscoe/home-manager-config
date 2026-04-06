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
    nvim-web-devicons
    diffview-nvim
    plenary-nvim
    telescope-nvim
  ];

  neovimPlugins = common.plugins ++ neovimExtraPlugins;
  pluginInfo = pkgs.neovimUtils.makeVimPackageInfo neovimPlugins;
  packDir = pkgs.neovimUtils.packDir {
    myNeovimPackages = pluginInfo.vimPackage;
  };

  python3Providers = pluginInfo.pluginPython3Packages;
  needsPython3Provider = python3Providers != [ ];
  python3Env = pkgs.python3.withPackages (
    ps: [ ps.pynvim ] ++ lib.concatMap (f: f ps) python3Providers
  );

  luaDeps = pluginInfo.luaDependencies;
  luaPathLuaRc =
    let
      luaEnv = pkgs.neovim-unwrapped.lua.withPackages (_: luaDeps);
      generatedLuaPath = pkgs.neovim-unwrapped.lua.pkgs.getLuaPath luaEnv;
      generatedLuaCPath = pkgs.neovim-unwrapped.lua.pkgs.getLuaCPath luaEnv;
    in
    ''
      package.path = "${generatedLuaPath}" .. ";" .. package.path
      package.cpath = "${generatedLuaCPath}" .. ";" .. package.cpath
    '';

  providerLuaRc =
    lib.concatStringsSep "\n" (
      [
        "vim.g.loaded_python_provider = 0"
        "vim.g.loaded_node_provider = 0"
        "vim.g.loaded_ruby_provider = 0"
        "vim.g.loaded_perl_provider = 0"
      ]
      ++ lib.optional needsPython3Provider "vim.g.python3_host_prog = '${python3Env}/bin/python3'"
    );

  luaLspConfig = ''
    lua << EOF
    local blink_ok, blink = pcall(require, 'blink.cmp')
    if blink_ok then
      blink.setup({})
    end

    local telescope_ok, telescope = pcall(require, 'telescope')
    local telescope_builtin_ok, telescope_builtin = pcall(require, 'telescope.builtin')
    if telescope_ok then
      telescope.setup({})
    end

    local function run_telescope(picker, opts)
      if not telescope_builtin_ok then
        vim.notify('Telescope is not available', vim.log.levels.WARN)
        return
      end
      local fn = telescope_builtin[picker]
      if type(fn) ~= 'function' then
        vim.notify('Telescope picker is not available: ' .. picker, vim.log.levels.WARN)
        return
      end
      fn(opts or {})
    end

    local function git_root()
      local root = vim.fn.systemlist('git rev-parse --show-toplevel')[1]
      if vim.v.shell_error == 0 and root and root ~= "" then
        return root
      end
      return nil
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

      local rust_check_command = vim.env.NVIM_RUST_CHECK_COMMAND
      if not rust_check_command or rust_check_command == "" then
        rust_check_command = 'clippy'
      end

      local rust_check_extra_args = {}
      if vim.env.NVIM_RUST_PEDANTIC ~= '0' then
        rust_check_extra_args = { '--', '-W', 'clippy::pedantic' }
      end

      if lspconfig.rust_analyzer then
        lspconfig.rust_analyzer.setup({
          capabilities = capabilities,
          on_attach = on_attach,
          settings = {
            ['rust-analyzer'] = {
              check = {
                command = rust_check_command,
                extraArgs = rust_check_extra_args,
              },
            },
          },
        })
      end

      local servers = { 'ts_ls', 'nil_ls', 'aiken', 'pyright' }
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

    vim.keymap.set('n', '<C-t>', function()
      if not telescope_builtin_ok then
        vim.notify('Telescope is not available', vim.log.levels.WARN)
        return
      end
      local ok = pcall(telescope_builtin.git_files, { show_untracked = true })
      if not ok then
        telescope_builtin.find_files()
      end
    end, { silent = true, desc = 'Find files' })
    vim.keymap.set('n', '<C-b>', function()
      run_telescope('buffers')
    end, { silent = true, desc = 'List buffers' })
    vim.keymap.set('n', '<C-h>', function()
      run_telescope('live_grep', { cwd = git_root() })
    end, { silent = true, desc = 'Live grep in git root' })

    local function current_diffview_file(view)
      local current_buf = vim.api.nvim_buf_get_name(0)
      if current_buf ~= "" and vim.fn.filereadable(current_buf) == 1 then
        return vim.fn.fnamemodify(current_buf, ':p')
      end

      if not view or type(view.cur_entry) ~= 'function' then
        return nil
      end

      local ok_entry, entry = pcall(view.cur_entry, view)
      if not ok_entry or not entry then
        return nil
      end

      local git_root = view.adapter and view.adapter.ctx and view.adapter.ctx.toplevel or nil
      local candidates = {
        entry.absolute_path,
        entry.path,
        entry.left and entry.left.absolute_path or nil,
        entry.left and entry.left.path or nil,
        entry.right and entry.right.absolute_path or nil,
        entry.right and entry.right.path or nil,
      }

      for _, candidate in ipairs(candidates) do
        if type(candidate) == 'string' and candidate ~= "" then
          if vim.fn.filereadable(candidate) == 1 then
            return vim.fn.fnamemodify(candidate, ':p')
          end
          if git_root then
            local rooted_candidate = git_root .. '/' .. candidate
            if vim.fn.filereadable(rooted_candidate) == 1 then
              return vim.fn.fnamemodify(rooted_candidate, ':p')
            end
          end
        end
      end

      return nil
    end

    vim.keymap.set('n', '<leader>dt', function()
      if vim.fn.exists(':DiffviewOpen') ~= 2 or vim.fn.exists(':DiffviewClose') ~= 2 then
        vim.notify('Diffview is not available', vim.log.levels.WARN)
        return
      end

      local ok, lib = pcall(require, 'diffview.lib')
      local view = ok and lib.get_current_view and lib.get_current_view() or nil
      if view then
        local file_to_open = current_diffview_file(view)
        vim.cmd('DiffviewClose')
        if file_to_open then
          vim.cmd('edit ' .. vim.fn.fnameescape(file_to_open))
        end
      else
        local file_to_focus = current_diffview_file(nil)
        if file_to_focus then
          vim.cmd('DiffviewOpen --selected-file=' .. vim.fn.fnameescape(file_to_focus))
        else
          vim.cmd('DiffviewOpen')
        end
      end
    end, { silent = true, desc = 'Toggle Diffview' })

    vim.keymap.set('n', '<leader>dT', function()
      if vim.fn.exists(':DiffviewOpen') ~= 2 then
        vim.notify('Diffview is not available', vim.log.levels.WARN)
        return
      end

      local file_to_focus = current_diffview_file(nil)
      if file_to_focus then
        vim.cmd('DiffviewOpen origin/main --selected-file=' .. vim.fn.fnameescape(file_to_focus))
      else
        vim.cmd('DiffviewOpen origin/main')
      end
    end, { silent = true, desc = 'Diffview against origin/main (focus current file)' })
    vim.diagnostic.config({
      virtual_text = true,
    })
    EOF
  '';

  initVimContent = ''
    set packpath^=${packDir}
    set runtimepath^=${packDir}
  ''
  + "\n"
  + vimSettings
  + "\n"
  + common.extraConfig
  + "\n"
  + luaLspConfig;

  initLuaContent =
    lib.concatStringsSep "\n\n" (
      lib.optional (luaDeps != [ ]) luaPathLuaRc
      ++ [ providerLuaRc ]
      ++ [
        "vim.cmd.source(vim.fn.stdpath('config') .. '/init.vim')"
      ]
      ++ pluginInfo.pluginAdvisedLua
    );
in
{
  home.packages =
    [ pkgs.neovim-unwrapped ]
    ++ lib.optionals needsPython3Provider [ python3Env ]
    ++ pluginInfo.runtimeDeps;

  home.sessionVariables.EDITOR = "nvim";

  home.shellAliases.vimdiff = "nvim -d";

  xdg.configFile."nvim/init.lua".text = initLuaContent;
  xdg.configFile."nvim/init.vim".text = initVimContent;
}
