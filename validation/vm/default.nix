{ lib, writeText, writeShellApplication, python3, qemu, OVMF, cloud-utils, openssh, git, openssl, runCommand }:
let
  source = lib.cleanSource ./.;
  runtime = writeText "xps-restore-runtime.json" (builtins.toJSON {
    qemu = "${qemu}/bin/qemu-system-x86_64";
    qemu-img = "${qemu}/bin/qemu-img";
    cloud-localds = "${cloud-utils}/bin/cloud-localds";
    firmware = "${OVMF.fd}/FV/OVMF_CODE.fd";
    variables = "${OVMF.fd}/FV/OVMF_VARS.fd";
  });
  tool = writeShellApplication {
    name = "xps-restore-test";
    runtimeInputs = [ python3 openssh git openssl ];
    text = ''
      export HM_RESTORE_RUNTIME=${runtime}
      export PYTHONDONTWRITEBYTECODE=1
      exec ${python3}/bin/python3 -I ${source}/vm.py "$@"
    '';
  };
in tool.overrideAttrs (old: {
  passthru = (old.passthru or { }) // {
    tests = runCommand "restore-vm-boundaries" { nativeBuildInputs = [ python3 ]; } ''
      export PYTHONDONTWRITEBYTECODE=1
      ${python3}/bin/python3 -I ${source}/test_vm.py
      touch "$out"
    '';
  };
})
