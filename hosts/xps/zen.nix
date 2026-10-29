{
  config,
  pkgs-unstable,
  zenPackage,
  ...
}:
let
  # Only the application is declarative. The imported profile contains private,
  # mutable browsing data and must never be copied into a Nix derivation.
  browser = zenPackage.override {
    extraPolicies.DisableAppUpdate = true;
    nativeMessagingHosts = [ pkgs-unstable.tridactyl-native ];
  };
in
{
  home.packages = [ (config.lib.nixGL.wrap browser) ];
}
