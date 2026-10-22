{ lib, pkgs-unstable, ... }:
let
  # Keep notebook libraries together, separate from the OS Python, Neovim's
  # provider, the interactive Python/pip pair and project environments.
  interpreter = pkgs-unstable.python3;
  pip = import ./python-pip.nix {
    inherit lib pkgs-unstable;
    python = interpreter;
  };
  python =
    (interpreter.withPackages (
      ps:
      (with ps; [
        jupyterlab
        notebook
        jupyter-console
        qtconsole
        ipykernel
        ipywidgets
        jupyter-lsp
        numpy
        pandas
        matplotlib
        openpyxl
        selenium
        pdfplumber
        sqlite-utils
        httpx
      ])
      ++ [ pip ]
      ++ ps.httpx.optional-dependencies.cli
    )).override
      {
        # IPython propagates the pin's older pip. Replace it only in this runtime
        # environment, keeping the already-built notebook libraries unchanged.
        requiredPythonModules =
          packages:
          builtins.filter (package: package.outPath != interpreter.pkgs.pip.outPath) (
            interpreter.pkgs.requiredPythonModules packages
          );
      };
  tools =
    pkgs-unstable.runCommand "xps-jupyter-tools"
      {
        nativeBuildInputs = [ pkgs-unstable.makeWrapper ];
      }
      ''
        mkdir -p "$out/bin"
        # Export the packaged desktop entries/icons after retiring their old pip
        # copies. Jupyter itself resolves data/config through its own Python prefix.
        ln -s ${python}/share "$out/share"
        for executable in ${python}/bin/jupyter* ${python}/bin/ipython* \
          ${python}/bin/jlpm ${python}/bin/pdfplumber ${python}/bin/pdf2txt.py \
          ${python}/bin/dumppdf.py ${python}/bin/sqlite-utils ${python}/bin/httpx; do
          [ -x "$executable" ] || continue
          makeWrapper "$executable" "$out/bin/$(basename "$executable")" \
            --set PYTHONNOUSERSITE 1 --unset PYTHONPATH \
            --prefix PATH : "$out/bin:${python}/bin"
        done
      '';
in
{
  home.packages = [ tools ];
  home.file.".local/share/jupyter/kernels/python3/kernel.json".text = builtins.toJSON {
    argv = [
      "${python}/bin/python"
      "-m"
      "ipykernel_launcher"
      "-f"
      "{connection_file}"
    ];
    display_name = "Python 3 (Home Manager)";
    language = "python";
    env = {
      PYTHONNOUSERSITE = "1";
      PYTHONPATH = "";
    };
    metadata.debugger = true;
  };
}
