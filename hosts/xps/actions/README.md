# XPS audio and action palette

Home Manager owns `xps-audio`, its user service, and `xps-actions`. Ubuntu's
PulseAudio server and its existing Bluetooth/routing modules stay in place.
No system installer, sudo permission or audio-server restart is needed.

## Open controls

- **Super+P**: unified XPS action palette (Command+P inside XPS Desktop).
- **Super+Shift+A**: audio controls (Command+Shift+A inside XPS Desktop).
- **Super+Space**: existing applications/windows launcher, including **XPS
  actions** and **Audio controls** entries.
- Click **xps** in Polybar for actions. Right-click output volume for audio.
- **Mic ready / Mic muted / Mic LIVE** is shown in Polybar. Left-click opens
  audio controls; right-click toggles all input mute. LIVE means an uncorked
  PulseAudio capture stream on a non-monitor input, not proof of saved recording.
- Hardware volume/mute keys now use the same PulseAudio controls; the microphone
  mute key toggles all real inputs. The shortcut reference includes these keys.

Audio controls include Bluetooth pairing/connection, output/input selection, volume/gain, mute, Bluetooth
music/headset profiles, a quiet left/right tone test, and the full per-app mixer.
Unavailable HDMI ports and output-monitor sources are hidden from input/output
selection as appropriate. Choosing a new device moves existing streams as well
as selecting the default; streams that vanish or reject moving are left to the
server and the per-app mixer. Changing a headset profile is explicit, with a
confirmation for the playback-quality tradeoff when enabling the headset mic.
The test tone never unmutes an output implicitly and never records a microphone.

`xps-audio up|down|mute|mic-mute|output|input|profiles|mixer|test` also work from a
terminal in the same user session. `status`, `mic-status` and `json` inspect the
service's cached state. `systemctl --user status xps-audio` and
`journalctl --user -u xps-audio` diagnose it. A disconnected/stale service reports
`Audio ?` / `Mic ?`, not a reassuring enabled/muted status.

## Routing and microphone behavior

The service subscribes to PulseAudio events, coalesces bursts, and publishes a
five-second freshness heartbeat without requerying devices on every heartbeat.
It restarts on failure and reconnects after an audio-server restart.

An explicitly selected device is remembered in private mutable state under
`~/.local/state/xps-audio`, outside Git/Nix. When that device returns, it is
selected again and playback/capture streams are moved. A disconnected or invalid
default falls back to an available device; built-in speakers take priority over
other fallback outputs. Existing valid routing changes made in the full mixer
are not continually overridden while the preferred device stays connected.
PulseAudio's existing routing modules can also choose devices independently.

Device switching does not unmute outputs or reset their stored volumes. Keyboard
volume/gain adjustments preserve channel offsets and clamp each channel between
0 and 100%. Existing values above 100% are only clamped when adjusted.

Global microphone mute is a saved latch, applied to newly arriving non-monitor
sources after their arrival event. Explicit unmute unmutes the present real
inputs. This is a software convenience, not a hardware privacy switch: event
handling is asynchronous, and external mixers/apps can also change audio state.
The indicator uses observed mute/capture state rather than assuming a click
succeeded. No automatic microphone test or recording runs in the background.

To forget device preferences, stop `xps-audio.service`, move its private
`preferences.json` aside, then start it again. Existing PulseAudio mute/volume
state is not reset by that operation.

## Unified actions

The fixed 21-entry registry groups Sound, Connections, Privacy, Desktop, System
and Session tasks. Search text filters actions; it is never executed as a shell
command. Existing Wi-Fi/Bluetooth/KDE Connect menus and camera controls are
reused. Camera/power confirmations stay in their owning menus. Backup and
hardware-health entries show saved status; they do not start uploads or hardware
tests. Tailnet status does not connect/disconnect or alter DNS.

Reports open in the managed Alacritty and remain visible. The existing app
launcher, application command search and shortcut reference remain available.
The Lake Bled theme and XPS Desktop/Picom performance policy are preserved.
`xps-actions --list` prints the literal registry for inspection.

## Validation

Synthetic tests cover stale devices, cancellation, literal argv execution,
100% volume limits, monitor-source exclusion, stream moves, reconnect preferences,
input mute inheritance and palette reports. The full native xps regression suite
and Home Manager build pass.

Live Sony WH-1000XM4 tests use a zero-volume silent playback stream to verify
moving existing playback to speakers/headphones, disconnect fallback and preferred
reconnect, headset-mic mute inheritance and restoration of A2DP music mode. All
pre-test volumes and mute states are restored; no microphone audio is captured.
The Sony output remains selected/preferred after that test. The corrected audible left/right test was confirmed by the user in the correct
ears at a comfortable level, without changing the device volume. The PCM signal
has fade-in/out and bounded amplitude, with no extra stream attenuation. Visual
menu checks are recorded in the task verification artifacts. Those tests do not validate every future Bluetooth device/profile.
