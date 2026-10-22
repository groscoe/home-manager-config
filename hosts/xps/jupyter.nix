{ pkgs-unstable, ... }:
let
  # Keep notebook libraries together, separate from the OS Python, Neovim's
  # provider, project environments and the existing OpenAI CLI installation.
  python = pkgs-unstable.python3.withPackages (ps: (with ps; [
    jupyterlab
    notebook
    jupyter-console
    qtconsole
    ipykernel
    ipywidgets
    jupyter-lsp
    openpyxl
    selenium
    pdfplumber
    sqlite-utils
    httpx
  ]) ++ ps.httpx.optional-dependencies.cli);
  tools = pkgs-unstable.runCommand "xps-jupyter-tools" {
    nativeBuildInputs = [ pkgs-unstable.makeWrapper ];
  } ''
    mkdir -p "$out/bin"
    for executable in ${python}/bin/jupyter* ${python}/bin/ipython* \
      ${python}/bin/jlpm ${python}/bin/pdfplumber ${python}/bin/pdf2txt.py \
      ${python}/bin/dumppdf.py ${python}/bin/sqlite-utils ${python}/bin/httpx; do
      [ -x "$executable" ] || continue
      makeWrapper "$executable" "$out/bin/$(basename "$executable")" \
        --set PYTHONNOUSERSITE 1 --unset PYTHONPATH \
        --prefix PATH : "$out/bin:${python}/bin"
    done
  '';
in {
  home.packages = [ tools ];
  home.file.".local/share/jupyter/kernels/python3/kernel.json".text =
    builtins.toJSON {
      argv = [ "${python}/bin/python" "-m" "ipykernel_launcher" "-f" "{connection_file}" ];
      display_name = "Python 3 (Home Manager)";
      language = "python";
      env = { PYTHONNOUSERSITE = "1"; PYTHONPATH = ""; };
      metadata.debugger = true;
    };
}
