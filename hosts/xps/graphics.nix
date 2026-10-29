{ config, nixGLPackages, ... }:
{
  # Match each wrapped application's Mesa libraries to the host's Nixpkgs pin.
  # Ubuntu still owns the kernel, X server and global graphics environment.
  targets.genericLinux.nixGL = {
    packages = nixGLPackages;
    defaultWrapper = config.personal.hardware.graphicsWrapper;
  };
}
