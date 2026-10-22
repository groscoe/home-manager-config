{ pkgs, lib }:
{
  text = pkgs.fantasque-sans-mono;
  icons = pkgs.stdenvNoCC.mkDerivation {
    pname = "material-design-iconic-font";
    version = "2.2.0";
    src = pkgs.fetchzip {
      url = "https://github.com/zavoloklom/material-design-iconic-font/releases/download/2.2.0/material-design-iconic-font.zip";
      stripRoot = false;
      hash = "sha256-xYoJjzxnjnCXZES7UVhNsk3T9MazK1KlNFzcTBsWv+M=";
    };
    installPhase = ''
      install -Dm644 fonts/Material-Design-Iconic-Font.ttf \
        "$out/share/fonts/truetype/Material-Design-Iconic-Font.ttf"
    '';
    meta = {
      description = "The original icon font used by the XPS Material bar";
      homepage = "https://zavoloklom.github.io/material-design-iconic-font/";
      license = lib.licenses.ofl;
      platforms = lib.platforms.all;
    };
  };
}
