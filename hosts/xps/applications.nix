{ config, pkgs-unstable, ... }:
let
  # Keep the newer version already installed on xps until the unstable pin
  # catches up. The checksum comes from Google's signed APT package index.
  chrome = pkgs-unstable.google-chrome.overrideAttrs {
    version = "155.0.8059.84";
    src = pkgs-unstable.fetchurl {
      url = "https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_155.0.8059.84-1_amd64.deb";
      hash = "sha256-j70q5pzffumLdRPDOWp7Xgb5dPhiX91ZDfMJHdDD6d4=";
    };
  };
in {
  imports = [ ./jupyter.nix ./application-discovery.nix ];
  # Personal applications use the existing unstable pin. Ubuntu retains its
  # system utilities, hardware integration and service implementations.
  home.packages = with pkgs-unstable; [
    git
    git-lfs
    curl
    wget
    rsync
    ffmpeg
    pandoc
    htop
    postgresql_14
    sqlite
    yq
    whois
    traceroute
    wakeonlan
    netcat-openbsd
    inotify-tools
    unzip
    zip
    meson
    ninja
    cursor-cli
    chrome
    libreoffice
    krita
    transmission_4-gtk
    rhythmbox
    shotwell
    dropbox-cli
    kdePackages.kdeconnect-kde
    kdePackages.ktouch
  ];

  # Codex remains npm-managed by choice. Fish already includes this directory;
  # sessionPath also exposes it to other login shells and desktop launchers.
  home.sessionPath = [ "${config.home.homeDirectory}/.npm/bin" ];
  home.sessionVariables.NPM_CONFIG_PREFIX = "${config.home.homeDirectory}/.npm";

  # Preserve the existing launcher path while moving its implementation from
  # the vendor's per-user updater to the pinned package. Credentials stay local.
  home.file.".local/bin/cursor-agent".source =
    "${pkgs-unstable.cursor-cli}/bin/cursor-agent";
}
