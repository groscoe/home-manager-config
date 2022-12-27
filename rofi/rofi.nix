{ pkgs, ... }:
  {
      # See: https://github.com/nix-community/home-manager/blob/master/modules/programs/rofi.nix
      enable = true;

      plugins = with pkgs; [
        rofi-calc
        rofi-bluetooth
        rofi-file-browser
        rofi-power-menu
        rofi-pulse-select
      ];

      font = "Source Code Pro 24";

      cycle = true; # cycle through the result list

      theme = "solarized_alternate";

      extraConfig = {
        #modes = "drun,run,window,power-menu,bluetooth,pulse-select,file-browser-extended,calc";
        modes = "drun,run,window,file-browser-extended,calc";
        drun-use-desktop-cache = true;
        drun-reload-desktop-cache = true;
      };
    }
