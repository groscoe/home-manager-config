# Monthly battery and SSD health

`services.hardware-health` supplies the same read-only tracker on Linux/systemd
and macOS/launchd. Both host profiles enable it. The host profile selects its
internal NVMe controller explicitly; USB/external drives are never scanned.
No battery charge setting, SSD setting, self-test or benchmark is requested.

```sh
hardware-health --status
hardware-health --status --json
hardware-health --record
hardware-health --test-notification
```

The scheduler tries daily while awake, and at user-manager/login startup. A
successful reading is taken only once per UTC calendar month. A missed month
is sampled at the next available run; historical measurements are not invented.
The daily check also retries pending notifications and, on mbp, fetches xps's
saved report using noninteractive SSH. It does not wake a sleeping computer.
Manual `--record` takes an additional reading. Short-lived jobs do not require
keeping a resident Python process running.

## Measurements and alerts

- Linux battery health is full-charge capacity / design capacity, using either
  charge or energy units consistently. A zero cycle count is reported as
  unavailable. macOS uses System Information's **maximum capacity** percentage,
  not the current charge or IORegistry's normalized `MaxCapacity=100` value.
- Hashed battery/controller identities separate replacement hardware from old
  history. Raw device serial numbers are not written to the history. Changing
  battery measurement sources starts a new comparison series.
- The default battery alerts are a drop of 5 percentage points within 45 days,
  or 10 within 105 days, and a service/fair/poor condition when available.
  These are configurable operational thresholds, not manufacturer failure
  criteria. Fuel-gauge estimates can fluctuate; an alert asks for confirmation.
- NVMe alerts cover failed SMART status/critical warnings, any new media/data
  integrity error, a 1-point reduction in spare capacity, spare at/below its
  threshold, endurance consumed reaching 90%, or wear increasing 5 points in
  45 days / 10 in 105 days. A reset of cumulative counters is reported separately.
- A rise of 100 generic error-log entries also requests inspection. Those
  entries may include unsupported commands and do not themselves prove media
  failure. Lifetime writes, powered-on hours, temperature and unsafe shutdowns
  are saved as context; unsafe shutdown counts alone do not produce an alarm.
- Device-open/read failures are visible collection alerts. They are never
  replaced by zero counters or recorded as a successful baseline. Partial
  readings are visible in status and retried daily. Existing device warnings
  are preserved while a source is unreadable.

The monthly cadence can detect changes only at readings; it is not continuous
failure prediction. xps's existing native smartd remains responsible for its
more frequent checks. History cannot prove a battery is physically undamaged.

## Notifications and history

Linux uses Dunst via `notify-send`; macOS uses its native AppleScript notification
interface, matching the existing backup notifier. Allow its notifications in
System Settings if macOS suppresses them. A successful notification command
confirms API acceptance, not that a person saw it. Run the test command from the
real login session to check presentation. Failed commands remain pending and
are retried; unchanged accepted alerts are suppressed until they clear/change.

mbp also reads `hardware-health --status --json` on xps over LAN SSH (port 2222).
It relays active xps alerts to the Mac desktop without changing xps's readings,
keys or notification state. An ordinary offline/unreachable xps is tolerated;
a previously known report older than 62 days produces a stale-report warning.
Each machine still tracks independently. Forwarding needs the existing Mac SSH
key/Keychain setup to work noninteractively. No messages leave these machines.

State lives in `$XDG_STATE_HOME/hardware-health/history.json` (normally
`~/.local/state/hardware-health`), mode 0600 in a newly created 0700 directory.
It contains up to 240 successful snapshots plus the latest partial reading,
alerts, notification delivery state and cached remote alerts. It is ordinary
home data included by the existing backup scope, not a Nix-store configuration.
Writes are atomic and locked. Invalid history is preserved rather than silently
reset; `failure.json` and the job log explain the problem.

Linux diagnostics:

```sh
systemctl --user status hardware-health.timer hardware-health.service
journalctl --user -u hardware-health.service
```

Mac diagnostics:

```sh
launchctl print gui/$(id -u)/org.nix-community.home.hardware-health
cat ~/Library/Logs/hardware-health-error.log
```

## One-time Linux SMART access

Home Manager cannot grant root permissions itself. Keep native smartmontools
installed, then explicitly run:

```sh
~/.local/bin/install-hardware-health-access
hardware-health --record
```

The installer validates root ownership/permissions of native executables, tests
the exact query, backs up any previous rule and installs only this sudo command
for the configured user/controller:

```text
/usr/sbin/smartctl -i -H -A -j /dev/nvme0
```

No wildcard, other device, tests, firmware or setting command is allowed. It
validates sudoers and tests a noninteractive read as the configured user. On
failure it restores the previous rule; it prints a root-only backup/rollback
path. The explicit `--check` installer option performs the preflight only.
Re-run the installer after intentionally changing the configured controller or
native smartctl path. macOS uses the pinned Nix tool without sudo or a root helper.

## Recovery and portability

Restore the history with the rest of the user's home, activate the relevant host
profile, verify the configured internal controller, and repeat Linux access
setup if needed. New hardware identifiers create new baselines automatically.
Disable battery monitoring for a desktop/VM and provide that machine's real
NVMe controllers; do not copy xps's hardware selection blindly. The Linux collector
uses sysfs plus native smartmontools, without an Ubuntu release assumption;
systemd, a notification server and the native sudo installer tools are prerequisites.
