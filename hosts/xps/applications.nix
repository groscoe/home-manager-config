{ pkgs-unstable, ... }:
{
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
    codex
    cursor-cli
  ];

  # Preserve the existing launcher path while moving its implementation from
  # the vendor's per-user updater to the pinned package. Credentials stay local.
  home.file.".local/bin/cursor-agent".source =
    "${pkgs-unstable.cursor-cli}/bin/cursor-agent";
}
