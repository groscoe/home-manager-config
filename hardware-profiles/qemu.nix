# Example virtual hardware; confirm the output with xrandr in the actual guest.
{
  graphicsWrapper = "mesa";
  displayOutput = "Virtual-1";
  wifiInterface = null;
  battery = null;
  acAdapter = null;
  backlightDevice = null;
  nvmeDevices = [ ];
  dpi = 96;
  scale = 1;
  cursorSize = 24;
  localTmuxPrefix = ";";
  keyboardLayout = "us";
  keyboardOptions = [ "caps:escape" ];
  keyboardRemaps = [ ];
  tablet = null;
}
