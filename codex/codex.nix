{ pkgs, lib, ... }:
let
  codexVersion = "0.118.0";
  codexTag = "rust-v${codexVersion}";
  codexAssets = {
    x86_64-linux = {
      url = "https://github.com/openai/codex/releases/download/${codexTag}/codex-x86_64-unknown-linux-musl.tar.gz";
      sha256 = "sha256-5wfqZde7vEagSv5zG/PBSlt3UiEAzr+LuTz/uVz0YQs";
      bin = "codex-x86_64-unknown-linux-musl";
    };
    aarch64-darwin = {
      url = "https://github.com/openai/codex/releases/download/${codexTag}/codex-aarch64-apple-darwin.tar.gz";
      sha256 = "bad3c2c83b874b767ce86af64f4f005bc14dea79f2d8cac37cfa6eb77710c717";
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
