{ config, lib, ... }:
let
  cfg = config.personal.hardware;
  identifier = lib.types.strMatching "[A-Za-z0-9][A-Za-z0-9_.-]*";
  optionalDevice = description: lib.mkOption {
    type = lib.types.nullOr identifier;
    default = null;
    inherit description;
  };
in {
  options.personal.hardware = lib.mkOption {
    description = "Explicit Linux hardware and display policy; null means that device is absent.";
    default = { };
    type = lib.types.submodule {
      options = {
        graphicsWrapper = lib.mkOption { type = lib.types.enum [ "mesa" "mesaPrime" "nvidia" "nvidiaPrime" ]; default = "mesa"; };
        displayOutput = optionalDevice "Internal XRandR output; also the default Polybar output.";
        wifiInterface = optionalDevice "Wireless interface used by the bar; null omits its module.";
        battery = optionalDevice "Battery power-supply name; null omits battery UI and monitoring.";
        acAdapter = optionalDevice "Mains power-supply name paired with the battery.";
        backlightDevice = optionalDevice "Built-in LCD backlight; null disables the hardware-specific VNC server.";
        cameraController = lib.mkOption {
          default = null;
          description = "Dedicated PCI camera controller for optional built-in-camera blocking; null disables controls.";
          type = lib.types.nullOr (lib.types.submodule {
            options = {
              address = lib.mkOption { type = lib.types.strMatching "[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\\.[0-7]"; };
              driver = lib.mkOption { type = lib.types.strMatching "[A-Za-z0-9_-]+"; };
              virtualCameraName = lib.mkOption { type = lib.types.strMatching "[A-Za-z0-9 ._-]+"; };
              vendor = lib.mkOption { type = lib.types.strMatching "0x[0-9a-f]{4}"; };
              device = lib.mkOption { type = lib.types.strMatching "0x[0-9a-f]{4}"; };
            };
          });
        };
        nvmeDevices = lib.mkOption {
          type = lib.types.listOf (lib.types.strMatching "/dev/nvme[0-9]+");
          default = [ ];
          description = "Explicit internal NVMe controllers for read-only health monitoring.";
        };
        dpi = lib.mkOption { type = lib.types.ints.positive; default = 96; };
        scale = lib.mkOption { type = lib.types.ints.between 1 4; default = 1; };
        cursorSize = lib.mkOption { type = lib.types.ints.positive; default = 24; };
        localTmuxPrefix = lib.mkOption { type = lib.types.enum [ "ç" ";" ]; default = ";"; };
        keyboardLayout = lib.mkOption {
          type = lib.types.strMatching "[A-Za-z0-9_,()-]+";
          default = "us";
        };
        keyboardOptions = lib.mkOption {
          type = lib.types.listOf (lib.types.strMatching "[A-Za-z0-9_:+-]+");
          default = [ ];
        };
        keyboardRemaps = lib.mkOption {
          type = lib.types.listOf lib.types.str;
          default = [ ];
          description = "xmodmap expressions, passed as literal arguments rather than shell code.";
        };
        tablet = lib.mkOption {
          default = null;
          type = lib.types.nullOr (lib.types.submodule {
            options = {
              rotation = lib.mkOption { type = lib.types.enum [ "none" "half" "cw" "ccw" ]; default = "none"; };
              area = lib.mkOption { type = lib.types.listOf lib.types.ints.unsigned; };
            };
          });
        };
      };
    };
  };
  config.assertions = [ {
    assertion = (cfg.battery == null) == (cfg.acAdapter == null);
    message = "Declare both personal.hardware.battery and acAdapter, or omit both.";
  } {
    assertion = cfg.backlightDevice == null || cfg.displayOutput != null;
    message = "A configured LCD backlight requires an explicit internal displayOutput.";
  } {
    assertion = lib.mod cfg.dpi cfg.scale == 0;
    message = "The X11 DPI must divide evenly by the integer toolkit scale.";
  } {
    assertion = cfg.tablet == null || builtins.length cfg.tablet.area == 4;
    message = "A tablet area needs four coordinates.";
  } ];
}
