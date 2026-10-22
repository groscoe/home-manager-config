{
  lib,
  pkgs-unstable,
  python,
}:
let
  original = python.pkgs.pip;
in
# Use the published, hash-checked wheel until the existing unstable input
# includes this release. The override applies to each interpreter separately.
# https://pypi.org/project/pip/26.2.2/
if lib.versionAtLeast original.version "26.2.2" then
  original
else
  python.pkgs.buildPythonPackage {
    pname = "pip";
    version = "26.2.2";
    format = "wheel";
    src = pkgs-unstable.fetchurl {
      url = "https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl";
      hash = "sha256-/X9N+oGQ4BQBO58I8+lz9OTCb/0XmiBIlVM6clSBOnA=";
    };
    pythonImportsCheck = [ "pip" ];
    meta = original.meta // {
      outputsToInstall = [ "out" ];
    };
  }
