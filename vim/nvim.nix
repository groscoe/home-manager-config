args@{ config, pkgs, lib, ... }:
  let
    vimConfigs = import ./vim.nix args;

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

      vimSettings = vimscriptFromSettings (vimConfigs.settings // {
        undodir = [ "~/.nvimhistory" ];
      });
  in {
    enable = true;
    plugins = vimConfigs.plugins;
    extraConfig = vimSettings + "\n" + vimConfigs.extraConfig;
  }
