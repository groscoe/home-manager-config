{ lib, stdenv, fetchurl, pkg-config, dbus, zig }:

stdenv.mkDerivation {
  pname = "whereami";
  version = "0.4.0";

  src = fetchurl {
    url = "https://codeload.github.com/georgemandis/whereami/tar.gz/2729cbe2aa55c423c74742d1200aa06bf922b05c";
    name = "whereami-0.4.0.tar.gz";
    hash = "sha256-nvSeaBPLg1W0DTDh3VpRenm7yQTmUn+csJ0Ftf+lqMw=";
  };

  nativeBuildInputs = [ zig ] ++ lib.optionals stdenv.hostPlatform.isLinux [ pkg-config ];
  buildInputs = lib.optionals stdenv.hostPlatform.isLinux [ dbus ];

  postPatch = if stdenv.hostPlatform.isDarwin then ''
    substituteInPlace build.zig --replace-fail '"codesign"' '"/usr/bin/codesign"'
  '' else ''
    # The CLI reads queued messages itself. Dispatching first consumes the signal.
    substituteInPlace src/platform/linux.zig \
      --replace-fail dbus_connection_read_write_dispatch dbus_connection_read_write
  '';

  dontConfigure = true;
  buildPhase = ''
    runHook preBuild
    export ZIG_GLOBAL_CACHE_DIR="$TMPDIR/zig-global-cache"
    ${if stdenv.hostPlatform.isDarwin then ''
      zig build bundle -Doptimize=ReleaseSafe -Dtarget=aarch64-macos -Dmacos-sdk="$SDKROOT"
    '' else ''
      zig build -Doptimize=ReleaseSafe
    ''}
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    ${if stdenv.hostPlatform.isDarwin then ''
      mkdir -p "$out/Applications" "$out/bin"
      cp -R zig-out/whereami.app "$out/Applications/"
      ln -s ../Applications/whereami.app/Contents/MacOS/whereami "$out/bin/whereami"
    '' else ''
      install -Dm755 zig-out/bin/whereami "$out/bin/whereami"
      install -Dm644 zig-out/share/applications/whereami.desktop "$out/share/applications/whereami.desktop"
    ''}
    runHook postInstall
  '';

  # Darwin's fixup phase would modify the already signed executable.
  dontFixup = stdenv.hostPlatform.isDarwin;

  meta = {
    description = "Show your location using native OS location services";
    homepage = "https://github.com/georgemandis/whereami";
    license = lib.licenses.mit;
    mainProgram = "whereami";
    platforms = [ "aarch64-darwin" "x86_64-linux" ];
  };
}
