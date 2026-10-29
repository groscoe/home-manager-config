# Device inventory verified on the physical xps, 2026-10-29.
{
  graphicsWrapper = "mesa";
  displayOutput = "eDP-1";
  wifiInterface = "wlp0s20f3";
  battery = "BAT0";
  acAdapter = "AC";
  backlightDevice = "intel_backlight";
  nvmeDevices = [ "/dev/nvme0" ];
  dpi = 192;
  scale = 2;
  cursorSize = 48;
  localTmuxPrefix = "ç";
  keyboardLayout = "br";
  keyboardOptions = [ "caps:escape" ];
  keyboardRemaps = [ "keycode 20 = minus underscore minus underscore backslash bar backslash" ];
  tablet = {
    rotation = "ccw";
    area = [ 0 5050 15200 14550 ];
  };
}
