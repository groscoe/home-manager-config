{ ... }: {
  programs.ssh = {
    enable = true;
    # Keep Apple's Keychain-aware client on macOS and Ubuntu's client on xps.
    package = null;
    enableDefaultConfig = false;
  };
}
