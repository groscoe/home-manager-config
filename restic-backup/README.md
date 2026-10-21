# Shared Restic backups through Home Manager

The same `restic-backup` command runs on Linux and macOS. The module schedules
it through a systemd user timer or a launchd agent, respectively.

```nix
imports = [ ./restic-backup ];
services.restic-backup = {
  enable = true;
  paths = [ config.home.homeDirectory ]
    ++ lib.optionals (!isDarwin) [ "/vault" ];
  requiredMounts = lib.optionals (!isDarwin) [ "/vault" ];
  # Defaults: intervalHours = 24; requireAC = true; thresholdGB = 20;
};
```

Commands:

```sh
restic-backup --dry-run       # default; no snapshot/upload
restic-backup --run           # manual backup, with interactive large-change gate
restic-backup --status        # last verified success, attempt and private log path
```

Hourly checks request one completed backup every 24 hours while awake and on AC.
They do not wake the laptop. A Linux timer catches up after sleep; the Mac agent
runs at login and on the hourly calendar interval. Missing required mounts defer
the backup. Switching to battery stops an automatic run and leaves it eligible
for retry. A local lock prevents overlapping scheduled/manual runs.

Every backup first compares Restic's own dry-run selection with a matching
parent snapshot for the same hostname and directory list. When adding a new
root, an old snapshot covering a subset of these roots on this same machine can
serve as the parent; the new root counts as added data. Snapshots from another
machine or containing unrelated roots are never used. An exact directory-list
match takes precedence over a subset.

If added/grown data, removed/shrunk data, or new repository data exceeds 20
decimal GB, an interactive `--run` asks for `yes`. Scheduled runs do not bypass
this gate: they stop, record `needs-confirmation`, and notify the desktop when
available. Run `restic-backup --run` to review and approve the change. The command
also accepts `--threshold-gb NUMBER` for an intentional one-off threshold.
No snapshots are pruned or deleted. Removed data means omitted from the new
snapshot; previous snapshots remain intact.

The first automatic run after a long gap may need this manual approval. Source
read errors or inconsistent inventories stop the backup; they are not treated
as success or hidden by adding exclusions. A success is recorded only after a
new repository snapshot covering every configured root has been verified.

`excludes.txt` retains the existing Mac rules and common exclusions, with Linux
additions in `default.nix`. These exclude caches, dependencies, build output,
`.git` histories and selected installers/VM disks. Home Manager excludes only
links still pointing at installed managed files. Local replacements and the
Home Manager source repository remain eligible. Review the rules if you need
unpublished Git history or currently excluded app data.

Each snapshot uses `--one-file-system`; additional mounts require their own entry
in `paths`. The defaults cover the user's home plus `/vault` on xps and the home
on the Mac. This is a personal-data backup, not a system image or a consistent
export of databases outside these roots. `/nix` and Docker's system volumes are
not included. Credentials and the repository password live outside Nix in the
existing `/etc/restic-env` and `/etc/restic-password`; retain an independent
recoverable copy of the repository password. Never copy those values into Nix.
The command rejects publicly readable credential files. Root-owned Linux files
may use a private user group (root:groscoe 0640); Mac user-owned files use 0600.

Private status and bounded logs live under `~/.cache/restic-backup` (excluded
from backups). A preview does not advance last-success. Failures and interrupted
runs remain eligible for retry. Repeated large-change notices are limited to
once per day. There is no automatic repository unlock or retention/prune job.

On macOS, manual commands and launchd jobs have separate privacy contexts.
For example, an interactive backup started in iTerm can report `operation not
permitted` for `Photo Booth Library` or `Photos Library.photoslibrary` even
when the background job can read them. Enable iTerm in System Settings > Privacy
& Security > Full Disk Access (add `/Applications/iTerm.app` if missing), then
fully quit and reopen iTerm after saving any terminal work. Run
`restic-backup --dry-run` from the reopened terminal to verify access. macOS
requires the user to grant this permission; Home Manager manages the job and
command, while macOS retains the privacy grants.

Verify background access separately, including the protected library contents,
not just their parent `Pictures` folder. A launchd exit code of zero can mean
that the hourly check deferred because a recent backup already exists; check
its actual preflight/backup log before treating that as a successful access
test. Source read errors stop the backup and do not advance last-success.

Tests use temporary local repositories and synthetic files; no production
credentials, snapshots or user files are used:

```sh
python3 -m unittest discover -s restic-backup/tests -v
```

Protected files on xps are handled by a small root system timer, installed once
with `~/.local/bin/install-restic-backup-export`. It makes private, root-owned,
group-readable archives under the encrypted `/vault/.restic-protected` directory.
It does not run Restic, upload anything, change source permissions or restart
source services. Unchanged archives are reused; the manifest is refreshed hourly
on AC. The user backup requires a complete export less than 26 hours old before
substituting these archives for the protected originals. The protected set is the
work Tailscale state (excluding its runtime log/DNS/DERP cache), the Desktop LUKS
header backup, and the 586 MB Onebus PostGIS directory. Database files are archived
only while `onebus-postgis` is stopped; starting it requires adding a database-dump
workflow before further automatic backups can succeed. Runtime sockets are omitted.
The tar archives preserve original ownership and permissions for recovery. They
contain secrets and must stay private; do not publish them or extract them over
live services. This does not read a block device or update a LUKS header.

The one-time installer copies immutable Nix-store code/config into root-owned
system locations, verifies the units, and prints its protected backup/rollback.
After changing `protectedSources`, rerun it to synchronize the root exporter.
