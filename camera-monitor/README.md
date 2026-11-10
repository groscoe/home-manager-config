# Camera access monitor

Home Manager runs `camera-monitor.service` in the user manager, including while using SSH.
Polybar's camera label opens the read-only Rofi process list; the launcher also
provides **Camera access**. The Lake Bled theme is inherited.

- `Cam ACCESS`: an observed consumer holds a video/subdevice/media handle.
- `Cam —`: no consumer handle observed with system coverage.
- `Cam — (user)`: no consumer handle observed, but only user coverage is available.
- `Cam ?`: some processes could not be inspected; absence of access is unknown.
- `Cam !`: monitor unavailable, failed, or its last sample is over eight seconds old.
- `No cam`: no video/media device nodes were discovered.

This is access monitoring, not proof of streaming, recording or a privacy barrier.
The monitor never opens a camera. It discovers device numbers through sysfs rather
than assuming `/dev/video0`; kernel uevents refresh hotplug inventory. Linux V4L
major 81 is also filtered in-kernel to cover newly created video/subdevices. Media nodes
can also represent non-camera hardware, so an open media handle is conservative.

Run `install-camera-monitor-access` once to install the optional system collector.
It prompts for sudo, copies the immutable Nix-store source to a root-owned location,
validates and enables a fixed systemd service, and backs up prior configuration.
It changes no camera permissions, drivers, relay settings or device state. The
collector uses a pinned libbpf CO-RE event engine and metadata-only process scans.
Its bounded capabilities include BPF/PERFMON for tracing and PTRACE/DAC_READ_SEARCH
for process metadata, without SYS_ADMIN. It has no camera DeviceAllow exception
and is denied opening camera devices by systemd device policy. It exposes only metadata in root-owned
`/run/camera-monitor/status.json` (0640, your private group; directory 0750).
Re-run the installer after updating collector code through Home Manager; the
protected copy is deliberately independent of a user's mutable profile.

Without a fresh trusted collector, coverage falls back to explicitly sampled
**current-user only** mode (which can miss brief accesses). A fresh failed eBPF
collector instead reports its tracing error as unavailable.
Root's relay and other users then cannot be inspected. A system process can use
the physical camera without appearing in this fallback mode. Rofi always shows
which coverage is active. Protected/uninspectable processes still make coverage
partial, including with the collector. A virtual-only relay producer is listed as
infrastructure rather than a consumer; if it opens physical nodes, it counts as
access. Stop the collector with
`sudo systemctl disable --now camera-monitor-collector.service`; fallback remains
explicit. Installation failures restore the saved configuration. Brokers such as PipeWire are identified
but a browser tab/website or broker's downstream client is not inferred. A process
can hold a handle without streaming. Successful `do_dentry_open` returns generate
kernel events; failed opens and O_PATH references are excluded. `__fput` generates
a release event when the final reference to an open file is released, including
dup/fork/SCM_RIGHTS cases. A release is attributed to its original opener when
known, not necessarily the process dropping the last descriptor. Handles existing
before attachment are discovered by an initial scan; unknown release events only
trigger reconciliation, never an invented opener notification.

The ring buffer captures PID, UID, process name and process start identity in
kernel context, so a brief opener can exit before userspace handles the event.
Executable paths are enriched from /proc only if the same process still exists;
otherwise explicitly unavailable. Names identify a broker, not its downstream
browser tab. Events do not establish recording/streaming.

Current-holder snapshots are refreshed after kernel events (50 ms burst debounce),
on hotplug, and every **60 seconds** to reconcile inherited/transferred handles.
There is no continuous two-second process scan in normal eBPF mode. One-second
collector heartbeats publish freshness without scanning processes. The user
service waits on inotify for atomic status replacements; Polybar can still refresh
its label on its existing interval while Dunst/history process the queued events.
Kernel events remain available even when an application opened and closed between
UI refreshes. The root ring journal retains 200 records. An incomplete kernel or
UI journal, a collector restart gap, failed attachment or stale heartbeat is
shown as degraded/unavailable, never silently as complete system coverage.
Loss warnings persist for the relevant running monitor session; restarting does
not reconstruct events that were missed. Hotplug inventory registration can have
a small race for dynamically assigned media majors; history is not an audit-grade
or tamper-proof record.
There is no claim of tamper resistance against programs running as your user.

Successful open/final-release events generate Dunst notifications. Bursts are
summarized in one bounded notification, with each event retained in the journal;
Rofi shows the latest eight known consumer events, including already-ended brief
accesses. A long-lived holder found at startup is listed in current holders even
if its opening event predates attachment. State and at most 200 transition events are kept in
`~/.local/state/camera-monitor/`, owner-only. Events contain UTC time, process name,
PID/start identity, executable and device names; no command lines, URLs, frames or
audio. Notifications are escaped; process names never enter Polybar markup.
PID start identity distinguishes reused PIDs. Stale service state fails visibly.

Commands: `camera-monitor status`, `details`, `json`, `probe` (fresh sample), `menu`.
`systemctl --user status camera-monitor` inspects the service.
## Built-in camera controls

The xps hardware profile declares the dedicated Intel IPU6 PCI controller by
address, driver and vendor/device ID. A profile without `cameraController`
(such as xps-vm) has no controls installer. This switch covers the **built-in
camera only**, not a subsequently connected USB webcam or microphones.

After Home Manager activation run `install-camera-controls` once with sudo.
The installer copies immutable sources/configuration to a root-owned directory,
backs up changed files, validates the sudo policy, and installs the boot guards.
It leaves the camera's current state unchanged. `--self-test` additionally starts
a temporary camera stream discarded to `/dev/null`, blocks it, checks that a new
capture fails/stalls, unblocks, and verifies fresh capture succeeds. It refuses
the test if another camera application is observed. No video is saved. Hardware
and live boot enforcement are tested; a real reboot still needs a separate check.

Click **Cam**, select **Block built-in camera…** or **Allow built-in camera…**,
then confirm. Esc/Cancel performs no action. CLI equivalents are
`camera-monitor block` and `camera-monitor unblock`. The narrowly scoped sudo
policy grants only those two literal commands through the fixed root-owned
backend, with no arbitrary device, code path, shell command or extra arguments.
It does not grant general systemctl, sysfs, module or device-permission access.
This is a user-controlled software privacy switch: software running as your
account can invoke the same two authorized actions. It is not a physical shutter
or protection against root/the account owner deliberately re-enabling the camera.

Blocking saves the relay camera’s ACLs, denies access to its root-owned virtual
video nodes, stops the relay, applies an exclusive driver override and detaches
the verified PCI camera controller. A udev rule removes `uaccess` while blocked so
seat management cannot silently regrant the virtual-device permissions. This interrupts fresh physical camera frames,
including for applications that already hold descriptors. Applications may
freeze, retain already-delivered frames or require reopening after unblocking.
No application is killed. Kernel modules, GRUB, EFI and initramfs are untouched.

The requested block is stored root-owned under `/var/lib/camera-monitor-control/`.
A hardware-specific udev rule prevents normal driver attachment when blocked;
a boot service reapplies a saved block, and a relay condition prevents startup.
A root administrator can override this. Unblocking reattaches the same controller
and restores the virtual-device ACLs/mode and the relay's previous active/inactive state. Conflicting hardware IDs,
drivers or pre-existing overrides are refused rather than overwritten.

`Cam BLOCKED` requires a saved block **and** a live detached controller with the
expected override, plus denied permissions on matching virtual-camera nodes.
This also prevents a newly opened normal-user capture from receiving an old
buffered virtual-camera frame. Already-open applications can retain frames they
received earlier; the switch cannot erase those. `Cam BLOCK ?` means requested/actual policy is inconsistent or
unverifiable; do not rely on it. `+ access` preserves visibility of open handles,
including other cameras. A failed operation never silently reports success.

Recovery from an interrupted operation, in a terminal:

```sh
sudo /usr/bin/python3 -I /usr/local/libexec/camera-monitor/control.py unblock
```

Re-run the installer after changing the hardware profile or protected backend.
A saved block cannot be silently retargeted to another controller. Installer
backups under `/var/backups/camera-privacy-*` contain a destination manifest and
prior files. Keep the guards installed while a block is saved; unblock before
removing them.

## eBPF installation and validation

Activate Home Manager, then rerun `install-camera-monitor-access` to upgrade the
protected collector. The installer validates immutable sources, verifies backups,
retains the engine closure through a root-owned Nix GC root, installs the bounded
unit, and waits for a *new* healthy eBPF stream. Failure restores the old files,
GC root and prior service state. It prints a root-only rollback script. It changes
no control backend, sudo policy, driver binding, permissions or camera state.

This backend requires kernel BTF, BPF tracing/trampolines, the two supported kernel
functions, and permission to attach to them. Attachment/load failures, including
a lockdown policy that forbids tracing, fail visibly. Hook semantics can change
with kernel upgrades: rerun the brief-open test after upgrading the kernel;
attachment alone is not a semantic compatibility test. CO-RE relocates data fields at load time, not hardcoded offsets.

Live validation on xps's Ubuntu 6.8.0-138 kernel includes queued open/release
capture for `/dev/null` with 0/1/5/10/25 ms holds after each process exits. The
separate camera-node test uses fifteen unprivileged brief opens of the virtual
camera exposed to applications, checks root and user journals, and never requests
or saves frames. Camera-control unit regressions and immutable-source hashes are
checked independently. No boot/GRUB/EFI or firmware change is required.

The 2026-11-10 installed-service test captured **15 opens and 15 final releases**
on `/dev/video0`, across 0/1/5/10/25 ms holds, with zero kernel losses and all
records reaching the user's persistent history. Dunst retained the camera
notifications. The Rofi control entry and filtered brief-event rows were visually
checked in an isolated display. All 148 personal regression cases passed,
including the unchanged camera-control tests. A real reboot was not required or
performed for this migration.

The controls installer does not restart or replace the independent monitoring
collector. Its self-test waits for a fresh system snapshot, including after a cold
start; a missing/stale status file produces a bounded readiness error before any
camera operation.

## Virtual-camera blocking verification

The block also saves the configured virtual camera’s ACLs and denies its device
permissions, preventing a new normal-user open from receiving buffered frames.
The udev rule removes uaccess while blocked. Unblocking restores the saved ACLs
and mode along with the physical driver and previous relay state. Existing apps
can retain frames already received; blocking cannot erase those. The indicator
requires both physical detachment and virtual access denial to report BLOCKED.
The controls installer leaves the monitoring collector untouched; its live test
waits for a fresh status snapshot before doing any camera operation.
