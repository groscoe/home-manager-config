{ pkgs, lib, ... }:
let
  codexVersion = "0.120.0";
  codexTag = "rust-v${codexVersion}";
  codexAssets = {
    x86_64-linux = {
      url = "https://github.com/openai/codex/releases/download/${codexTag}/codex-x86_64-unknown-linux-musl.tar.gz";
      sha256 = "sha256-IbCMyneEvlPTPG9Gz4l80rRAzaWNx5ElY9vGdrTRcBc=";
      bin = "codex-x86_64-unknown-linux-musl";
    };
    aarch64-darwin = {
      url = "https://github.com/openai/codex/releases/download/${codexTag}/codex-aarch64-apple-darwin.tar.gz";
      sha256 = "sha256-sQg8Q4t1L6KSBX+4xzX1jRMjFEo9655XQsToRRUslfA=";
      bin = "codex-aarch64-apple-darwin";
    };
  };
  codexAsset = codexAssets.${pkgs.stdenv.hostPlatform.system}
    or (throw "codex: unsupported system ${pkgs.stdenv.hostPlatform.system}");
  codexPackage = pkgs.stdenv.mkDerivation {
    pname = "codex";
    version = codexVersion;
    src = pkgs.fetchurl {
      url = codexAsset.url;
      sha256 = codexAsset.sha256;
    };
    sourceRoot = ".";
    unpackPhase = "tar -xzf $src";
    installPhase = ''
      runHook preInstall
      install -D -m 0755 ${codexAsset.bin} $out/bin/codex
      runHook postInstall
    '';
    dontConfigure = true;
    dontBuild = true;
    meta = with lib; {
      description = "OpenAI Codex CLI";
      homepage = "https://github.com/openai/codex";
      license = licenses.asl20;
      platforms = [ "x86_64-linux" "aarch64-darwin" ];
    };
  };
in {
  codexPackage = codexPackage;
}
