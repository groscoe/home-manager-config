# Ubuntu host policies

Home Manager owns user configuration. This companion tool owns selected
root-owned Ubuntu policies from the same source repository. It uses the existing
flake pin's Ansible Core, so no global Ansible or pip installation is needed.

The initial scope is deliberately small:

| Policy | Declared behavior |
| --- | --- |
| SSH X11 forwarding | Disabled; agent forwarding, TCP tunnels, authentication and port settings retain their existing behavior |
| systemd journal | At most 1 GiB of persistent journals and a maximum retention of 30 days |

`policies.json` lists the two destination files. Their contents are in `files/`.
This profile is reviewed for Ubuntu 22.04 on x86_64. Review and test it before
extending it to a different Ubuntu release or hardware profile.

From the repository on xps, inspect the current host:

```sh
nix run .#xps-host
# Equivalent explicit form:
nix run .#xps-host -- check
```

This compares contents, owner/group and permissions and shows any content diff.
Exit status 0 means both policies match; 1 means there is drift. An unsupported
host or unsafe file path fails before application. The check also validates a
candidate SSH configuration using a disposable host key, preserving every
effective SSH setting except the declared `X11Forwarding no` policy. It does not
change system configuration or services; its temporary key is removed afterward.

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

To restore a replaced file, copy the reported backup to its original destination
with sudo, retaining root ownership and mode 0644. Validate with
`sudo /usr/sbin/sshd -t` before `sudo systemctl reload ssh.service` for SSH, or run
`sudo systemctl restart systemd-journald.service` for journal changes. If the tool
created a previously absent file, removing that specific managed drop-in restores
the earlier layering; validate SSH before reloading it.

Verify the provisioner in a disposable directory:

```sh
nix build .#checks.x86_64-linux.xps-host
```

The tests use actual Ansible copy/file modules to exercise dry-run behavior,
application, original-content backups, idempotence and metadata repair. The
fixture root is confined to a temporary test directory and service commands are
skipped. The normal command exposes no fixture or arbitrary Ansible arguments.

This is the first host-policy module, not a complete OS bootstrap. Ubuntu and Nix
must already be installed, along with OpenSSH server, systemd and a sudo-capable
account. Firewall/UFW policy, PAM/SDDM fingerprint integration, package sources,
Nix daemon setup, mounts, service masks and protected hardware/export setup are
separate migration work. Host keys, authorized keys, passwords and fingerprint
enrollment remain state to restore or enroll separately. Neither these secrets
nor disk/encryption identifiers are included in the Nix source.

Ansible's [copy module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/copy_module.html)
provides atomic file replacement, validation and backups. Its
[check/diff modes](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)
are exercised by the fixture tests; the public `check` command additionally
performs the host and candidate SSH checks described above.
