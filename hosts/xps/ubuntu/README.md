# Ubuntu host policies

Home Manager owns user configuration. This companion tool owns selected
root-owned Ubuntu policies from the same source repository. It uses the existing
flake pin's Ansible Core, so no global Ansible or pip installation is needed.
Host inspection and PAM validation use Ubuntu's `/usr/bin/python3` with the host
PAM libraries. The Ansible controller and isolated Nix checks use pinned Nix
dependencies; this avoids mixing the two dynamic-library environments.

The declared scope is:

| Policy | Declared behavior |
| --- | --- |
| SSH X11 forwarding | Disabled; agent forwarding, TCP tunnels, authentication and port settings retain their existing behavior |
| systemd journal | At most 1 GiB of persistent journals and a maximum retention of 30 days |
| i3lock and SDDM | Fingerprint authentication with the existing password fallback and login/account restrictions |
| Sugar Candy 1.6 | Existing theme, image and fingerprint instructions, action, waiting and retry feedback |
| Nix startup | Persistent unit definitions in `/etc`, mount ordering and socket activation at boot |

`policies.json` lists the destination files. Their contents are in `files/`.
This profile is reviewed for Ubuntu 22.04 on x86_64. Review and test it before
extending it to a different Ubuntu release or hardware profile.

From the repository on xps, inspect the current host:

```sh
nix run .#xps-host
# Equivalent explicit form:
nix run .#xps-host -- check
```

This compares contents, owner/group and permissions and shows any content diff.
Exit status 0 means all policies match; 1 means there is drift. An unsupported
host or unsafe file path fails before application. The check also validates a
candidate SSH configuration using a disposable host key, preserving every
effective SSH setting except the declared `X11Forwarding no` policy. It does not
change system configuration or services; its temporary key is removed afterward.
It also checks authentication package prerequisites and exercises the declared
PAM control flow using synthetic modules and an isolated PAM configuration
directory. No password, fingerprint template or enrollment is read by this test.
Nix startup inspection checks the two regular unit files, the socket enablement
link and the absence of the retired boot workaround. Native systemd verifies
the declared candidate units before any application.

To apply the reviewed policy:

```sh
nix run .#xps-host -- apply
```

Run this as your normal user. Ansible asks for the sudo password in your terminal.
The same preflight runs first. Application creates the policy directories if
needed, sets root:root ownership with mode 0644, and saves timestamped backups of
existing files when their contents are replaced. The backup paths are printed.
The SSH fragment is validated before replacement and the complete SSH
configuration is checked before reload. SSH reloads only after a content or
metadata change to its file. Journald restarts only after its file changes.
A matching host requests neither service action. Home Manager activation never
invokes this privileged command automatically.
PAM and theme changes request no SDDM restart, logout or lock. They are read at
the next authentication or login screen. Keep an existing authenticated session
open when applying an intentional authentication policy change.
The Nix startup step creates a private rollback backup before replacing a unit
or link. It reloads systemd's definitions only when that step changes files;
it does not start, stop or restart the Nix daemon/socket. A matching startup
configuration creates no backup and requests no systemd reload.

To restore a replaced file, copy the reported backup to its original destination
with sudo, retaining root ownership and mode 0644. Validate with
`sudo /usr/sbin/sshd -t` before `sudo systemctl reload ssh.service` for SSH, or run
`sudo systemctl restart systemd-journald.service` for journal changes. If the tool
created a previously absent file, removing that specific managed drop-in restores
the earlier layering; validate SSH before reloading it.
For PAM/theme files, restore the printed backups to their original paths with
root:root ownership and mode 0644. Restore a changed authentication policy from
the still-open session before logging out. If a package update replaces a managed
PAM file, `check` reports drift; review the package's changes before reapplying.

Verify the provisioner in a disposable directory:

```sh
nix build .#checks.x86_64-linux.xps-host
```

The tests use actual Ansible copy/file modules to exercise dry-run behavior,
application, original-content backups, idempotence and metadata repair. The
fixture root is confined to a temporary test directory and service commands are
skipped. The normal command exposes no fixture or arbitrary Ansible arguments.
The Nix check also runs 17 real-libpam cases against synthetic modules: password
and fingerprint success, password fallback when the scanner fails or is missing,
both methods rejecting, maintenance/root restrictions and account rejection.

## Fingerprint login and theme restoration

Before applying to a fresh Ubuntu 22.04 installation, install the packages listed
in `authentication-packages.json`. The checker refuses to apply if a prerequisite
is missing. This module does not select a display manager, enable autologin,
install packages or start an authentication service. SDDM must already be the
chosen display manager and the usual Ubuntu PAM includes must exist.

The managed `kde_settings.conf` retains Sugar Candy and the existing disabled
autologin configuration. The full known working theme is vendored, including its
GPL license, authors and image. `sugar-candy-provenance.json` records version 1.6,
the upstream URL, file checksums and local modifications; its upstream commit is
unknown. This intentionally preserves the tested theme rather than fetching a
moving theme release. Edit these declared sources to change the login appearance.

For `groscoe`, an empty password followed by Enter (or **Use fingerprint** in
SDDM) starts the reader. A typed password follows the original password stack.
The instructions currently name the right index finger, matching xps's existing
enrollment. On replacement hardware, check reader support and enroll that finger
with `fprintd-enroll -f right-index-finger` as the user, then test with
`fprintd-verify`. Enrollment and biometric templates are never stored here. If
another account or finger is used, adjust the theme hint as well. Fingerprint
login may leave a password-protected desktop keyring locked.

The optional UI test uses Ubuntu Qt5/PyQt5 and a mock SDDM object. With
`python3-pyqt5`, `python3-pyqt5.qtquick`, `xvfb`, `xauth` and the theme's QML
prerequisites installed:

```sh
/usr/bin/python3 -I hosts/xps/ubuntu/tests/test_theme.py \
  hosts/xps/ubuntu/files/sugar-candy /tmp/xps-login-ui-test
```

It checks Enter/button submission, duplicate-submit prevention, waiting and
failure feedback, the normal password path, enrolled-account hints and layout.
It runs on a disposable Xvfb display, uses only a synthetic password and never
starts real login. Xvfb is stopped automatically, including after test failure.
The PAM tests can also run against Ubuntu's native library without sudo:

```sh
/usr/bin/python3 -I hosts/xps/ubuntu/pam_check.py
```

## Nix startup and bootstrap recovery

`nix-units/` contains the exact startup definitions used on xps. They live as
regular root-owned files in `/etc/systemd/system`, so systemd can read them before
the separate `/nix` volume is mounted. `RequiresMountsFor` orders socket/daemon
activation after the necessary Nix paths become available. The daemon executable
uses the multi-user default profile, so ordinary Nix version upgrades retain the
same service definition. Only the socket enablement link is managed; the daemon
service itself remains socket-activated.

`nix-startup.json` also describes the original Nix installer's unit/enablement
links. These specific links can be adopted without following or modifying their
targets in the Nix profile/store. Any different link target is refused for review.
The old `custom-start-nix-in-other-partition.service` workaround is removed only
if it matches the previously reviewed content/link; unknown custom content is
refused. Replaced regular files and link targets, ownership and permissions are
saved in a root-only `/var/backups/xps-nix-startup-*` directory. The printed
rollback command restores the exact previous objects, and refuses to overwrite
subsequent administrator changes. An application failure restores the prior
files automatically. New empty parent directories can remain after rollback.

Nix itself must already be installed in its multi-user default profile. Existing
mount/encryption configuration must make its paths available. This module does
not install Nix, declare disks or mounts, copy credentials, edit Nix settings,
change trusted users or update GRUB, EFI, kernels or initrds.

If startup is broken and `nix run` is unavailable, the same bounded helper can
run from an ordinary checkout using Ubuntu's Python, without a running Nix daemon:

```sh
cd ~/Projects/home-manager-config
/usr/bin/python3 -I hosts/xps/ubuntu/nix_startup.py check
sudo /usr/bin/python3 -I hosts/xps/ubuntu/nix_startup.py apply
```

Have `/nix` mounted/unlocked first. Application enables the socket for future
boots but preserves its current running/stopped state. If recovering an inactive
socket, explicitly start it afterward with `sudo systemctl start nix-daemon.socket`,
then verify with `nix store info --store daemon`. The helper prints the private
backup path and its standalone rollback command. The backup includes the rollback
helper, so restoration does not depend on this checkout or on a Nix store path.

The Nix check runs additional disposable startup fixtures for fresh installation,
read-only inspection, exact backups, idempotence, permission repair, known installer
links, obsolete-workaround retirement, partial-write failure recovery and rollback.
The fixtures never call systemd or alter real startup definitions.

This is the first host-policy module, not a complete OS bootstrap. Ubuntu and Nix
must already be installed, along with OpenSSH server, systemd and a sudo-capable
account. Firewall/UFW policy, package sources,
Nix installation/settings, mounts, service masks and protected hardware/export setup are
separate migration work. Host keys, authorized keys, passwords and fingerprint
enrollment remain state to restore or enroll separately. Neither these secrets
nor disk/encryption identifiers are included in the Nix source.

Ansible's [copy module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/copy_module.html)
provides atomic file replacement, validation and backups. Its
[check/diff modes](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)
are exercised by the fixture tests; the public `check` command additionally
performs the host and candidate SSH checks described above.
The [Linux-PAM API](https://github.com/linux-pam/linux-pam/blob/master/libpam/include/security/pam_appl.h)
provides `pam_start_confdir` for the temporary service files. The tests also
rewrite include paths to the temporary directory for Ubuntu's older libpam;
they never mount over or edit `/etc/pam.d`.
