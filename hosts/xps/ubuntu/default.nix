{
  lib,
  writeShellApplication,
  python3,
  python3Packages,
  runCommand,
  pam,
  geoclue2,
}:
let
  source = lib.cleanSource ./.;
  ansible = python3Packages.ansible-core;
  geoclue = geoclue2.overrideAttrs (old: {
    patches = old.patches ++ [ ./geoclue-whereami-authorization.patch ];
  });
  tool = writeShellApplication {
    name = "xps-host";
    runtimeInputs = [
      python3
      ansible
    ];
    text = ''
      mode="''${1:-check}"
      if [ "$#" -gt 0 ]; then shift; fi
      if [ "$#" -ne 0 ]; then
        echo "Usage: xps-host [check|apply]" >&2
        exit 2
      fi
      export PYTHONDONTWRITEBYTECODE=1
      export ANSIBLE_CONFIG=${source}/ansible.cfg
      case "$mode" in
        check)
          exec /usr/bin/python3 -I ${source}/check.py --geoclue ${geoclue}
          ;;
        apply)
          if (( EUID != 0 )); then
            exec /usr/bin/sudo -- "$0" apply
          fi
          /usr/bin/python3 -I ${source}/check.py --preflight --geoclue ${geoclue}
          exec ${ansible}/bin/ansible-playbook \
            --inventory localhost, --connection local \
            --extra-vars "xps_geoclue=${geoclue}" \
            --diff ${source}/playbook.yml
          ;;
        *)
          echo "Usage: xps-host [check|apply]" >&2
          exit 2
          ;;
      esac
    '';
  };
in
tool.overrideAttrs (old: {
  passthru = (old.passthru or { }) // {
    tests =
      runCommand "xps-host-tests"
        {
          nativeBuildInputs = [
            python3
            ansible
          ];
        }
        ''
          export HOME="$TMPDIR/home"
          mkdir -p "$HOME"
          export PYTHONDONTWRITEBYTECODE=1
          export ANSIBLE_NOCOLOR=1
          export ANSIBLE_CONFIG=${source}/ansible.cfg
          ${python3}/bin/python3 -I ${source}/pam_check.py \
            --library ${pam}/lib/libpam.so.0 --modules ${pam}/lib/security
          ${python3}/bin/python3 -I ${source}/tests/test_nix_startup.py
          ${python3}/bin/python3 -I ${source}/tests/test_host.py \
            --ansible ${ansible}/bin/ansible-playbook \
            --python ${python3}/bin/python3
          touch "$out"
        '';
  };
})
