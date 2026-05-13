{ pkgs, lib, ... }:
let
  atuinVersion = "18.16.1";
  atuinTag = "v${atuinVersion}";
  atuinAssets = {
    x86_64-linux = {
      url = "https://github.com/atuinsh/atuin/releases/download/${atuinTag}/atuin-x86_64-unknown-linux-musl.tar.gz";
      sha256 = "sha256-ru4W+qsSbS8RZYrUkgxz+oR5sl+9PiZXBFCvcxCqxwo=";
      bin = "atuin-x86_64-unknown-linux-musl/atuin";
    };
    aarch64-darwin = {
      url = "https://github.com/atuinsh/atuin/releases/download/${atuinTag}/atuin-aarch64-apple-darwin.tar.gz";
      sha256 = "sha256-Cj/cTPoYdY1qhylQYl8gQiM98EEqDBDQ2t8wv8O8bWs=";
      bin = "atuin-aarch64-apple-darwin/atuin";
    };
  };
  atuinAsset = atuinAssets.${pkgs.stdenv.hostPlatform.system}
    or (throw "atuin: unsupported system ${pkgs.stdenv.hostPlatform.system}");
  atuinPackage = pkgs.stdenv.mkDerivation {
    pname = "atuin";
    version = atuinVersion;
    src = pkgs.fetchurl {
      url = atuinAsset.url;
      sha256 = atuinAsset.sha256;
    };
    sourceRoot = ".";
    installPhase = ''
      runHook preInstall
      install -D -m 0755 ${atuinAsset.bin} $out/bin/atuin
      runHook postInstall
    '';
    dontConfigure = true;
    dontBuild = true;
    meta = with lib; {
      description = "Magical shell history";
      homepage = "https://github.com/atuinsh/atuin";
      license = licenses.mit;
      mainProgram = "atuin";
      platforms = [ "x86_64-linux" "aarch64-darwin" ];
    };
  };
in {
  atuinPackage = atuinPackage;
}
