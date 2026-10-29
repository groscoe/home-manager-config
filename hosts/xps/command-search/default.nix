{ config, pkgs, ... }:
let
  testBus = pkgs.writeText "command-search-test-bus.conf" ''
    <!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
      "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
    <busconfig>
      <type>session</type>
      <listen>unix:tmpdir=/tmp</listen>
      <auth>EXTERNAL</auth>
      <policy context="default">
        <allow own="*"/>
        <allow send_destination="*"/>
        <allow receive_sender="*"/>
      </policy>
    </busconfig>
  '';
  python = pkgs.python3.withPackages (ps: [
    ps.pygobject3
    ps.xlib
  ]);
  search = pkgs.stdenvNoCC.mkDerivation {
    pname = "xps-command-search";
    version = "1";
    dontUnpack = true;
    nativeBuildInputs = [
      pkgs.makeWrapper
      pkgs.gobject-introspection
    ];
    buildInputs = [ pkgs.glib ];
    installPhase = ''
      mkdir -p "$out/bin" "$out/share/xps-command-search"
      cp ${./search.py} "$out/share/xps-command-search/search.py"
      makeWrapper ${python}/bin/python3 "$out/bin/xps-command-search" \
        --prefix GI_TYPELIB_PATH : "${pkgs.glib.out}/lib/girepository-1.0" \
        --add-flags "-I $out/share/xps-command-search/search.py --rofi ${config.programs.rofi.finalPackage}/bin/rofi"
    '';
    doInstallCheck = true;
    nativeInstallCheckInputs = [
      pkgs.xvfb-run
      pkgs.dbus
    ];
    installCheckPhase = ''
      export GI_TYPELIB_PATH="${pkgs.glib.out}/lib/girepository-1.0"
      xvfb-run -a dbus-run-session --config-file=${testBus} -- ${python}/bin/python3 -I ${./test-runtime.py} \
        --script "$out/share/xps-command-search/search.py"
    '';
  };
in
{
  home.packages = [ search ];
}
