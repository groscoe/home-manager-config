"""Use the shared Rofi theme; require an explicit confirmation for power actions."""
import json
import subprocess
import sys


def choose(rofi, prompt, entries):
    result = subprocess.run([rofi, "-dmenu", "-i", "-no-custom", "-format", "i", "-p", prompt],
                            input="\n".join(entries) + "\n", text=True, capture_output=True)
    if result.returncode != 0 or not result.stdout.strip().isdigit():
        return None
    index = int(result.stdout.strip())
    return index if 0 <= index < len(entries) else None


def main():
    cfg = json.load(open(sys.argv[1]))
    entries = ["Lock screen", "Suspend", "Log out", "Restart", "Power off"]
    selected = choose(cfg["rofi"], "Session", entries)
    if selected is None:
        return
    if selected == 0:
        subprocess.run([cfg["locker"], "--color", "475263"], check=True)
        return
    if choose(cfg["rofi"], entries[selected] + "?", ["Cancel", "Confirm"]) != 1:
        return
    commands = {1: [cfg["systemctl"], "suspend"], 2: [cfg["i3msg"], "exit"],
                3: [cfg["systemctl"], "reboot"], 4: [cfg["systemctl"], "poweroff"]}
    subprocess.run(commands[selected], check=True)


if __name__ == "__main__":
    main()
