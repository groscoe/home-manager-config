"""Search desktop and tmux shortcuts. Reference rows never run their actions."""

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

CATEGORIES = ("Desktop", "tmux", "Copy mode", "Advanced")

GROUPS = (
    ("Open and navigate", (
        ("Terminal", "$mod+Return"), ("Launcher", "$mod+space"),
        ("Application command search", "$mod+Shift+slash"),
        ("Drop-down terminal", "$mod+g"), ("Focus left", "$mod+h"),
        ("Focus down", "$mod+j"), ("Focus up", "$mod+k"),
        ("Focus right", "$mod+l"),
        ("File browser", "Ctrl+Shift+space"), ("Focus parent", "$mod+a"),
    )),
    ("Workspaces", (
        ("Switch workspace", "$mod+1"),
        ("Send window to workspace", "$mod+Shift+1"),
    )),
    ("Arrange windows", (
        ("Move left", "$mod+Shift+h"), ("Move down", "$mod+Shift+j"),
        ("Move up", "$mod+Shift+k"), ("Move right", "$mod+Shift+l"),
        ("Fullscreen", "$mod+f"), ("Toggle floating", "$mod+Shift+space"),
        ("Split horizontally", "$mod+c"), ("Split vertically", "$mod+v"),
        ("Tabbed layout", "$mod+Shift+w"), ("Stacked layout", "$mod+Shift+s"),
        ("Toggle split layout", "$mod+Shift+e"),
        ("Resize mode", "$mod+r"), ("Close window", "$mod+Shift+q"),
    )),
    ("Session and capture", (
        ("Lock screen", "$mod+Shift+x"), ("Screenshot tool", "Ctrl+Print"),
        ("Show scratchpad", "$mod+minus"),
        ("Hide in scratchpad", "$mod+Shift+minus"),
    )),
)

# Used only when no tmux server is running. These match the declared setup;
# a running server always supplies its own tables instead.
DEFAULT_TMUX = {
    "prefix": {
        "c": "new-window", "n": "next-window", "p": "previous-window",
        "%": "split-window -h", '"': "split-window", "j": "select-pane -t .+1",
        "k": "select-pane -t .-1", "z": "resize-pane -Z", "d": "detach-client",
        "]": "paste-buffer -p", "w": "run-shell clipboard.py --buffer",
        "?": "list-keys -N", "[": "copy-mode",
    },
    "copy-mode-vi": {
        "Space": "begin-selection", "V": "select-line", "v": "rectangle-toggle",
        "y": "copy-pipe-and-cancel clipboard.py", "Enter": "copy-pipe-and-cancel clipboard.py",
        "/": "search-forward", "?": "search-backward", "n": "search-again",
        "N": "search-reverse", "g": "history-top", "G": "history-bottom",
        "Escape": "clear-selection", "q": "cancel",
        "MouseDragEnd1Pane": "copy-pipe-and-cancel clipboard.py",
        "DoubleClick1Pane": "select-word copy-pipe-and-cancel clipboard.py",
        "TripleClick1Pane": "select-line copy-pipe-and-cancel clipboard.py",
        "D": "copy-pipe-end-of-line-and-cancel clipboard.py",
        "A": "copy-pipe-and-cancel clipboard.py --append",
        "!": "copy-pipe-and-cancel clipboard.py --no-newline",
        "Y": "copy-pipe-and-cancel clipboard.py --paste",
        "M-y": "copy-pipe-and-cancel clipboard.py --paste",
    },
}

# category, group, label, table, key alternatives, required command fragment.
TMUX_ROWS = (
    ("tmux", "Windows", "New window", "prefix", ("c",), "new-window"),
    ("tmux", "Windows", "Next / previous window", "prefix", ("n", "p"), "window"),
    ("tmux", "Panes", "Split side by side", "prefix", ("%",), "split-window"),
    ("tmux", "Panes", "Split top and bottom", "prefix", ('"',), "split-window"),
    ("tmux", "Panes", "Next / previous pane", "prefix", ("j", "k"), "select-pane"),
    ("tmux", "Panes", "Zoom / unzoom pane", "prefix", ("z",), "resize-pane"),
    ("tmux", "Session and clipboard", "Detach; keep session running", "prefix", ("d",), "detach-client"),
    ("tmux", "Session and clipboard", "Paste tmux buffer", "prefix", ("]",), "paste-buffer"),
    ("tmux", "Session and clipboard", "Copy latest buffer to clipboard", "prefix", ("w",), "clipboard.py"),
    ("tmux", "Session and clipboard", "Full tmux key reference", "prefix", ("?",), "list-keys"),
    ("Copy mode", "Selection", "Enter copy mode", "prefix", ("[",), "copy-mode"),
    ("Copy mode", "Selection", "Start selection", "copy-mode-vi", ("Space",), "begin-selection"),
    ("Copy mode", "Selection", "Select whole line", "copy-mode-vi", ("V",), "select-line"),
    ("Copy mode", "Selection", "Toggle rectangular selection", "copy-mode-vi", ("v",), "rectangle-toggle"),
    ("Copy mode", "Selection", "Copy selection to client clipboard", "copy-mode-vi", ("y", "Enter"), "clipboard.py"),
    ("Copy mode", "Search and history", "Search forward / backward", "copy-mode-vi", ("/", "?"), "search-"),
    ("Copy mode", "Search and history", "Repeat search", "copy-mode-vi", ("n",), "search-again"),
    ("Copy mode", "Search and history", "Reverse search direction", "copy-mode-vi", ("N",), "search-reverse"),
    ("Copy mode", "Search and history", "History start / end", "copy-mode-vi", ("g", "G"), "history-"),
    ("Copy mode", "Leaving copy mode", "Clear selection", "copy-mode-vi", ("Escape",), "clear-selection"),
    ("Copy mode", "Leaving copy mode", "Exit copy mode", "copy-mode-vi", ("q",), "cancel"),
    ("Copy mode", "Mouse selection", "Copy dragged selection", "copy-mode-vi", ("MouseDragEnd1Pane",), "clipboard.py"),
    ("Copy mode", "Mouse selection", "Copy a word", "copy-mode-vi", ("DoubleClick1Pane",), "clipboard.py"),
    ("Copy mode", "Mouse selection", "Copy a line", "copy-mode-vi", ("TripleClick1Pane",), "clipboard.py"),
    ("Advanced", "Clipboard variants · copy mode", "Copy to end of line", "copy-mode-vi", ("D",), "copy-pipe-end-of-line"),
    ("Advanced", "Clipboard variants · copy mode", "Append selection to last copy", "copy-mode-vi", ("A",), "--append"),
    ("Advanced", "Clipboard variants · copy mode", "Copy without trailing newline", "copy-mode-vi", ("!",), "--no-newline"),
    ("Advanced", "Clipboard variants · copy mode", "Copy and paste into pane", "copy-mode-vi", ("Y", "M-y"), "--paste"),
)


def read_i3_tables(text):
    """Keep mode-local keys separate from global shortcuts."""
    tables = {"default": {}}
    mode, depth = "default", 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match_mode = re.match(r'^mode\s+"([^"]+)"\s*\{\s*$', stripped)
        if not depth and match_mode:
            mode, depth = match_mode[1], 1
            tables.setdefault(mode, {})
            continue
        match = re.match(r"^bindsym\s+(?:--\S+\s+)*(\S+)\s+(.+)$", stripped)
        if match:
            tables[mode][match.group(1).lower()] = match.group(2)
        if depth:
            depth += stripped.count("{") - stripped.count("}")
            if depth <= 0:
                mode, depth = "default", 0
    return tables


def read_bindings(text):
    return read_i3_tables(text)["default"]


def read_tmux_tables(text):
    tables = {}
    for line in text.splitlines():
        if not line.startswith("bind-key "):
            continue
        parts = shlex.split(line)
        if "-T" not in parts:
            continue
        offset = parts.index("-T")
        if len(parts) > offset + 3:
            table, key = parts[offset + 1:offset + 3]
            tables.setdefault(table, {})[key] = " ".join(parts[offset + 3:])
    return tables


def load_tmux(executable):
    try:
        tables = {}
        for table in ("prefix", "copy-mode-vi"):
            result = subprocess.run([str(executable), "list-keys", "-T", table],
                                    text=True, capture_output=True, timeout=3)
            if result.returncode:
                return DEFAULT_TMUX, "tmux stopped · showing the managed setup"
            tables.update(read_tmux_tables(result.stdout))
        return tables, "Live tmux tables · vi copy-mode keys"
    except (OSError, subprocess.TimeoutExpired):
        return DEFAULT_TMUX, "tmux unavailable · showing the managed setup"


def key_labels(binding, keyboard="xps", workspace_range=False):
    aliases = {"$mod": "⌘" if keyboard == "mac" else "Super", "return": "Enter",
               "space": "Space", "shift": "Shift", "ctrl": "Ctrl",
               "print": "Print", "minus": "−", "left": "←", "right": "→",
               "up": "↑", "down": "↓", "escape": "Esc", "slash": "/"}
    keys = [aliases.get(key.lower(), key.upper()) for key in binding.split("+")]
    if workspace_range:
        keys[-1] = "1…0"
    return keys


def tmux_key(key, keyboard="xps"):
    special = {"Space": "Space", "Enter": "Enter", "Escape": "Esc",
               "MouseDragEnd1Pane": "Drag & release", "DoubleClick1Pane": "Double-click",
               "TripleClick1Pane": "Triple-click"}
    if key in special:
        return [special[key]]
    if key.startswith("M-"):
        return ["Option" if keyboard == "mac" else "Alt", key[2:].upper()]
    if len(key) == 1 and key.isalpha():
        return (["Shift"] if key.isupper() else []) + [key.upper()]
    return [key]


def reference(text, query="", keyboard="xps", category=None, tmux_tables=None):
    bindings = read_bindings(text)
    query = query.casefold().strip()
    result = []
    for title, entries in GROUPS:
        focus_commands = [bindings.get("$mod+" + key) for key in "hjkl"]
        combine_focus = title == "Open and navigate" and focus_commands == [
            "focus left", "focus down", "focus up", "focus right"
        ]
        move_commands = [bindings.get("$mod+shift+" + key) for key in "hjkl"]
        combine_move = title == "Arrange windows" and move_commands == [
            "move left", "move down", "move up", "move right"
        ]
        rows = []
        for label, binding in entries:
            if combine_focus and binding in ("$mod+j", "$mod+k", "$mod+l"):
                continue
            if combine_move and binding in ("$mod+Shift+j", "$mod+Shift+k", "$mod+Shift+l"):
                continue
            command = bindings.get(binding.lower())
            if command is None:
                continue
            # Advertise the whole digit range only if all ten keys still exist.
            digits = "1234567890"
            all_digits = title == "Workspaces" and all(
                binding[:-1].lower() + digit in bindings for digit in digits
            )
            keys = key_labels(binding, keyboard, all_digits)
            arrows = False
            if combine_focus and binding == "$mod+h":
                label = "Focus window"
                keys[-1] = "H / J / K / L"
                command = "; ".join(focus_commands)
                arrows = [bindings.get("$mod+" + key) for key in ("left", "down", "up", "right")] == focus_commands
            if combine_move and binding == "$mod+Shift+h":
                label = "Move window"
                keys[-1] = "H / J / K / L"
                command = "; ".join(move_commands)
                arrows = [bindings.get("$mod+shift+" + key) for key in ("left", "down", "up", "right")] == move_commands
            rows.append({"label": label, "binding": binding,
                         "keys": keys, "command": command, "arrows": arrows})
        if rows:
            result.append({"title": title, "category": "Desktop", "rows": rows})

    rows = []
    for label, binding in (("Reload i3 configuration", "$mod+Shift+c"), ("Restart i3", "$mod+Shift+r")):
        if binding.lower() in bindings:
            rows.append({"label": label, "keys": key_labels(binding, keyboard),
                         "binding": binding, "command": bindings[binding.lower()]})
    if rows:
        result.append({"title": "Desktop configuration", "category": "Advanced", "rows": rows})
    resize = read_i3_tables(text).get("resize", {})
    if resize and bindings.get("$mod+r", "").startswith('mode "resize"'):
        rows = []
        candidates = (
            ("Resize window", ("left", "down", "up", "right"), ["Arrows"], "resize "),
            ("Larger resize steps", ("ctrl+left", "ctrl+down", "ctrl+up", "ctrl+right"), ["Ctrl", "Arrows"], "resize "),
            ("Increase / decrease vertical gaps", ("shift+k", "shift+j"), ["Shift", "K / J"], "gaps "),
            ("Increase / decrease horizontal gaps", ("shift+h", "shift+l"), ["Shift", "H / L"], "gaps "),
            ("Balance inner / outer gaps", ("$mod+shift+k", "$mod+shift+j"), key_labels("$mod+Shift+k", keyboard)[:-1] + ["K / J"], "gaps "),
            ("Finish resizing", ("return", "escape"), ["Enter / Esc"], "mode "),
        )
        for label, bindings_needed, keys, expected in candidates:
            if all(resize.get(key, "").startswith(expected) for key in bindings_needed):
                rows.append({"label": label, "keys": keys, "binding": "resize: " + ", ".join(bindings_needed),
                             "command": "; ".join(resize[key] for key in bindings_needed)})
        if rows:
            result.append({"title": "Resize mode", "category": "Advanced", "rows": rows,
                           "note": "Super+R to enter · Enter or Esc to finish".replace("Super", "⌘" if keyboard == "mac" else "Super")})

    if tmux_tables is not None:
        grouped = {}
        for tab, title, label, table, keys, expected in TMUX_ROWS:
            commands = tmux_tables.get(table, {})
            present = [key for key in keys if expected in commands.get(key, "")]
            if not present:
                continue
            # Avoid advertising the missing half of a paired action.
            if len(keys) > 1 and len(present) == 1:
                label = {
                    ("Next / previous window", "n"): "Next window",
                    ("Next / previous window", "p"): "Previous window",
                    ("Next / previous pane", "j"): "Next pane",
                    ("Next / previous pane", "k"): "Previous pane",
                    ("Search forward / backward", "/"): "Search forward",
                    ("Search forward / backward", "?"): "Search backward",
                    ("History start / end", "g"): "History start",
                    ("History start / end", "G"): "History end",
                }.get((label, present[0]), label)
            alternatives = [tmux_key(key, keyboard) for key in present]
            if all(len(alt) == 1 for alt in alternatives):
                labels = [" / ".join(alt[0] for alt in alternatives)]
            else:
                labels = [" or ".join("+".join(alt) for alt in alternatives)]
            if table == "prefix":
                labels = ["Prefix", "then", *labels]
            item = {"label": label, "keys": labels, "binding": table + ": " + " / ".join(present),
                    "command": "; ".join(commands[key] for key in present)}
            note = "Inside tmux · Prefix, then key" if tab == "tmux" else "tmux · vi copy-mode keys"
            group = grouped.setdefault((tab, title), {"title": title, "category": tab, "rows": [], "note": note})
            group["rows"].append(item)
        result.extend(grouped.values())

    filtered = []
    for group in result:
        # A nonempty query always searches every tab.
        if not query and category is not None and group["category"] != category:
            continue
        rows = []
        for row in group["rows"]:
            haystack = " ".join([group["category"], group["title"], group.get("note", ""), row["label"],
                                 row["binding"], row["command"], *row["keys"],
                                 "super command" if "$mod" in row["binding"] else "",
                                 "arrows" if row.get("arrows") else ""]).casefold()
            if all(word in haystack for word in query.split()):
                rows.append(row)
        if rows:
            filtered.append({**group, "rows": rows})
    return filtered


def run_window(config_path, palette, tmux_tables, tmux_status, check_ui=False, local_prefix="ç"):
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, Gio, GLib, Gtk, Pango

    app = Gtk.Application(application_id="org.groscoe.XpsShortcuts.Test" if check_ui else "org.groscoe.XpsShortcuts",
                          flags=Gio.ApplicationFlags.NON_UNIQUE if check_ui else Gio.ApplicationFlags.FLAGS_NONE)
    check_result = [0]

    def activate(application):
        if application.get_active_window():
            application.get_active_window().present()
            return
        window = Gtk.ApplicationWindow(application=application)
        window.set_title("Keyboard shortcuts — XPS")
        window.set_wmclass("xps-shortcuts", "XpsShortcuts")
        window.set_decorated(False)
        window.set_default_size(900, 860)
        window.set_position(Gtk.WindowPosition.CENTER)
        window.connect("key-press-event", lambda widget, event:
                       (window.close() or True) if event.keyval == Gdk.KEY_Escape else False)
        colours = palette
        style = """
        window { background: BACKGROUND; color: FOREGROUND; font-family: 'Noto Sans'; font-size: 14px; }
        .surface { background: PANEL; padding: 20px; }
        .heading { font-size: 22px; font-weight: 500; }
        .muted { color: MUTED; font-size: 12px; }
        .group-heading { color: LAVENDER; font-size: 12px; font-weight: 500; }
        .shortcut-row { border-bottom: 1px solid RAISED; padding: 6px 0; }
        label.keycap { color: FOREGROUND; background: RAISED; background-image: none; box-shadow: none; text-shadow: none; min-width: 0; min-height: 0; border: 1px solid EDGE; border-bottom: 2px solid EDGE; border-radius: 3px; padding: 2px 6px; font-family: 'Source Code Pro'; font-size: 12px; }
        entry { background: BACKGROUND; color: FOREGROUND; border: 1px solid EDGE; border-radius: 4px; padding: 8px; box-shadow: none; }
        entry:focus { border-color: LAVENDER; }
        button { background: RAISED; color: FOREGROUND; border: 0; border-radius: 4px; box-shadow: none; text-shadow: none; padding: 8px 12px; }
        button:hover { background: SELECTED; }
        button:checked { color: ACCENT; background: SELECTED; }
        .tabs button { padding: 9px 16px; }
        .result-scope { color: MUTED; font-size: 12px; }
        .prefix-note { background: BACKGROUND; padding: 12px; border-radius: 4px; }
        .prefix-note label.keycap { color: ACCENT; }
        """
        for token, key in {"BACKGROUND": "background", "FOREGROUND": "foreground",
                           "PANEL": "panel", "MUTED": "muted", "LAVENDER": "lavender",
                           "RAISED": "raised", "EDGE": "edge", "SELECTED": "selected",
                           "ACCENT": "accent"}.items():
            style = style.replace(token, colours[key])
        css = Gtk.CssProvider()
        css.load_from_data(style.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        outer.get_style_context().add_class("surface")
        window.add(outer)
        header = Gtk.Box(spacing=15)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(label="A shortcut away", xalign=0)
        title.get_style_context().add_class("heading")
        subtitle = Gtk.Label(label="Your desktop and terminal keys, in one place.", xalign=0)
        subtitle.get_style_context().add_class("muted")
        titles.pack_start(title, False, False, 0)
        titles.pack_start(subtitle, False, False, 0)
        header.pack_start(titles, True, True, 0)
        close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON)
        close.set_tooltip_text("Close · Esc")
        close.connect("clicked", lambda button: window.close())
        header.pack_end(close, False, False, 0)
        outer.pack_start(header, False, False, 0)
        tools = Gtk.Box(spacing=12)
        search = Gtk.SearchEntry(placeholder_text="Search all shortcuts…")
        tools.pack_start(search, True, True, 0)
        local = Gtk.RadioButton.new_with_label_from_widget(None, "XPS keyboard")
        mac = Gtk.RadioButton.new_with_label_from_widget(local, "Mac · VNC")
        for button in (local, mac):
            button.set_mode(False)
            tools.pack_start(button, False, False, 0)
        outer.pack_start(tools, False, False, 0)
        navigation = Gtk.Box(spacing=6)
        navigation.get_style_context().add_class("tabs")
        tabs = {}
        for category in CATEGORIES:
            button = Gtk.ToggleButton(label=category)
            navigation.pack_start(button, False, False, 0)
            tabs[category] = button
        outer.pack_start(navigation, False, False, 0)
        scope = Gtk.Label(xalign=0)
        scope.get_style_context().add_class("result-scope")
        outer.pack_start(scope, False, False, 0)
        view = {"category": "Desktop", "rendering": False}
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_propagate_natural_height(False)
        scroller.set_min_content_height(250)
        columns = Gtk.Box(spacing=28, homogeneous=True)
        scroller.add(columns)
        outer.pack_start(scroller, True, True, 0)
        def fill_key_line(box, parts):
            for child in box.get_children():
                child.destroy()
            for text, is_key in parts:
                label = Gtk.Label(label=text, xalign=0)
                label.get_style_context().add_class("keycap" if is_key else "muted")
                box.pack_start(label, False, False, 0)
            box.show_all()

        legend = Gtk.Box(spacing=6)
        prefix = Gtk.Box(spacing=6)
        fill_key_line(prefix, [("tmux prefix:", False), (local_prefix, True), ("Local / VNC", False),
                              ("·", False), (";", True), ("SSH", False), ("·", False),
                              ("Prefix", True), ("then", False), ("[", True), ("copy mode", False)])
        note = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        note.get_style_context().add_class("prefix-note")
        note.pack_start(legend, False, False, 0)
        note.pack_start(prefix, False, False, 0)
        outer.pack_start(note, False, False, 0)
        foot = Gtk.Label(label=tmux_status + "  ·  Esc to dismiss", xalign=0, wrap=True)
        foot.get_style_context().add_class("muted")
        outer.pack_start(foot, False, False, 0)

        def render_contents():
            keyboard = "mac" if mac.get_active() else "xps"
            for child in columns.get_children():
                child.destroy()
            boxes = [Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18) for _ in range(2)]
            query = search.get_text().strip()
            groups = reference(config_path.read_text(), query, keyboard, view["category"], tmux_tables)
            for category, button in tabs.items():
                button.set_active(not query and category == view["category"])
            count = sum(len(group["rows"]) for group in groups)
            scope.set_text(("All tabs" if query else view["category"]) + f" · {count} shortcuts")
            heights = [0, 0]
            for group in groups:
                section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                group_title = group["category"] + " · " + group["title"] if query else group["title"]
                heading = Gtk.Label(label=group_title.upper(), xalign=0, wrap=True)
                heading.get_style_context().add_class("group-heading")
                section.pack_start(heading, False, False, 0)
                if group.get("note"):
                    detail = Gtk.Label(label=group["note"], xalign=0, wrap=True)
                    detail.get_style_context().add_class("muted")
                    section.pack_start(detail, False, False, 0)
                for item in group["rows"]:
                    row = Gtk.Box(spacing=10)
                    row.get_style_context().add_class("shortcut-row")
                    description = Gtk.Label(label=item["label"], xalign=0)
                    description.set_line_wrap(True)
                    description.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                    description.set_max_width_chars(24)
                    description.set_size_request(140, -1)
                    description.set_tooltip_text(item["label"])
                    row.pack_start(description, True, True, 0)
                    caps = Gtk.Box(spacing=4)
                    labels = list(item["keys"])
                    if item.get("arrows"):
                        labels[-1] = "HJKL / arrows"
                    for key in labels:
                        cap = Gtk.Label(label=key)
                        cap.get_style_context().add_class("muted" if key == "then" else "keycap")
                        caps.pack_start(cap, False, False, 0)
                    row.pack_end(caps, False, False, 0)
                    section.pack_start(row, False, False, 0)
                idx = 0 if heights[0] <= heights[1] else 1
                heights[idx] += len(group["rows"]) + 2
                boxes[idx].pack_start(section, False, False, 0)
            if not groups:
                boxes[0].pack_start(Gtk.Label(label="No matching shortcuts", xalign=0), False, False, 0)
            for box in boxes:
                columns.pack_start(box, True, True, 0)
            if keyboard == "mac":
                fill_key_line(legend, [("⌘", True), ("Command → Super", False), ("·", False),
                                       ("Option", True), ("Option → Alt", False)])
            else:
                fill_key_line(legend, [("Super", True), ("Windows-logo key", False), ("·", False),
                                       ("Copy mode uses vi keys without", False), ("Prefix", True)])
            columns.show_all()
            scroller.get_vadjustment().set_value(0)

        def render(*unused):
            if view["rendering"]:
                return
            view["rendering"] = True
            try:
                render_contents()
            finally:
                view["rendering"] = False

        def select_tab(button, category):
            if view["rendering"]:
                return
            view["category"] = category
            search.set_text("")
            render()

        for category, button in tabs.items():
            button.connect("clicked", select_tab, category)

        search.connect("search-changed", render)
        local.connect("toggled", render)
        mac.connect("toggled", render)
        render()
        window.show_all()
        search.grab_focus()
        if check_ui:
            def inspect_ui():
                try:
                    assert len(columns.get_children()) == 2, "Initial render duplicated columns"
                    for category in CATEGORIES:
                        tabs[category].clicked()
                        assert view["category"] == category
                        assert scope.get_text().startswith(category + " · ")
                        assert "· 0 shortcuts" not in scope.get_text()
                        assert len(columns.get_children()) == 2, "Tab change duplicated columns"
                    search.set_text("clipboard")
                    render()
                    assert search.get_text() == "clipboard", "Tab update cleared global search"
                    assert scope.get_text().startswith("All tabs · ")
                    assert not any(button.get_active() for button in tabs.values())
                    headings = [section.get_children()[0].get_text() for box in columns.get_children()
                                for section in box.get_children()]
                    assert all(any(heading.startswith(category.upper() + " · ") for heading in headings)
                               for category in ("tmux", "Copy mode", "Advanced"))
                    tabs["Desktop"].clicked()
                    assert search.get_text() == ""
                    mac.set_active(True)
                    def labels(widget):
                        found = [widget.get_text()] if isinstance(widget, Gtk.Label) else []
                        for child in widget.get_children() if hasattr(widget, "get_children") else []:
                            found.extend(labels(child))
                        return found
                    assert "⌘" in labels(columns), "Mac modifier labels did not update"
                    assert {local_prefix, ";", "[", "Prefix", "⌘", "Option"}.issubset(labels(note)), "Footer keycaps lost their literal characters"
                    assert len(columns.get_children()) == 2
                    print("Shortcut UI checks passed: tabs, global search, Mac labels, two columns")
                except Exception:
                    import traceback
                    traceback.print_exc()
                    check_result[0] = 1
                finally:
                    window.close()
                    application.quit()
                return False
            GLib.idle_add(inspect_ui)

    app.connect("activate", activate)
    result = app.run([])
    return check_result[0] or result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--palette", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/i3/config")
    parser.add_argument("--tmux", type=Path, default=Path("tmux"))
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--search", default="")
    parser.add_argument("--local-prefix", choices=("ç", ";"), default="ç")
    parser.add_argument("--keyboard", choices=("xps", "mac"), default="xps")
    parser.add_argument("--list", action="store_true", help="Print the reference without opening a window")
    parser.add_argument("--check-runtime", action="store_true", help="Check the packaged GTK runtime without opening a window")
    parser.add_argument("--check-ui", action="store_true", help="Run isolated GTK interaction checks; use with xvfb-run")
    args = parser.parse_args()
    if args.check_runtime:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        print(f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()} available")
        return 0
    if args.check_ui:
        return run_window(args.config, json.loads(args.palette.read_text()), DEFAULT_TMUX,
                          "Synthetic tmux tables · isolated UI test", check_ui=True, local_prefix=args.local_prefix)
    if args.list:
        tables, _ = load_tmux(args.tmux)
        print(json.dumps(reference(args.config.read_text(), args.search, args.keyboard, args.category, tables), ensure_ascii=False, indent=2))
        return 0
    tables, status = load_tmux(args.tmux)
    return run_window(args.config, json.loads(args.palette.read_text()), tables, status, local_prefix=args.local_prefix)


if __name__ == "__main__":
    raise SystemExit(main())
