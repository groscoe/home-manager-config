"""The reference must follow actual global bindings without executing commands."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("theme_shortcuts", ROOT / "theme/shortcuts.py")
shortcuts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shortcuts)


class ShortcutReferenceTests(unittest.TestCase):
    def test_mode_binding_cannot_replace_global_binding(self):
        text = '''bindsym $mod+r mode "resize"
mode "resize" {
    bindsym $mod+r exec should-not-be-in-the-reference
    bindsym Return mode "default"
}
bindsym --release Ctrl+Print exec screenshot-tool
'''
        actual = shortcuts.read_bindings(text)
        self.assertEqual(actual["$mod+r"], 'mode "resize"')
        self.assertEqual(actual["ctrl+print"], 'exec screenshot-tool')
        self.assertNotIn("return", actual)

    def test_absent_binding_is_not_advertised(self):
        rows = shortcuts.reference("bindsym $mod+Return exec terminal\n")
        self.assertEqual([row["label"] for group in rows for row in group["rows"]], ["Terminal"])

    def test_reassigned_command_is_shown_literally_without_execution(self):
        command = "exec printf '$(never-run) <>&'"
        actual = shortcuts.reference("bindsym $mod+Return " + command)
        self.assertEqual(actual[0]["rows"][0]["command"], command)

    def test_workspace_range_requires_all_ten_bindings(self):
        one = "bindsym $mod+1 workspace 1\n"
        self.assertEqual(shortcuts.reference(one)[0]["rows"][0]["keys"][-1], "1")
        all_digits = "\n".join(f"bindsym $mod+{i} workspace {i}" for i in "1234567890")
        self.assertEqual(shortcuts.reference(all_digits)[0]["rows"][0]["keys"][-1], "1…0")

    def test_search_and_keyboard_context(self):
        text = "bindsym $mod+Return exec terminal\nbindsym $mod+Shift+x exec locker\n"
        result = shortcuts.reference(text, "lock", "mac")
        self.assertEqual(result[0]["rows"][0]["keys"], ["⌘", "Shift", "X"])
        self.assertEqual(shortcuts.reference(text, "missing action"), [])

    def test_focus_keys_combine_only_for_the_four_matching_commands(self):
        text = "\n".join(f"bindsym $mod+{key} focus {direction}" for key, direction in
                         zip("hjkl", ["left", "down", "up", "right"]))
        rows = shortcuts.reference(text)[0]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["keys"], ["Super", "H / J / K / L"])
        self.assertEqual(len(shortcuts.reference(text.replace("focus up", "exec other"))[0]["rows"]), 4)

    def test_global_search_ignores_the_selected_tab_and_matches_multiple_words(self):
        groups = shortcuts.reference("", "copy clipboard", category="Desktop", tmux_tables=shortcuts.DEFAULT_TMUX)
        self.assertTrue(groups)
        self.assertIn("Copy mode", {group["category"] for group in groups})
        self.assertTrue(all(group["category"] != "Desktop" for group in groups))
        self.assertEqual(shortcuts.reference("", category="Desktop", tmux_tables=shortcuts.DEFAULT_TMUX), [])

    def test_tmux_parser_preserves_case_quotes_and_literal_commands(self):
        text = r'''bind-key -T prefix \" split-window -c "#{pane_current_path}"
bind-key -T copy-mode-vi V send-keys -X select-line
bind-key -T copy-mode-vi v send-keys -X rectangle-toggle
bind-key -T prefix w run-shell "printf '$(never-run)'"
'''
        tables = shortcuts.read_tmux_tables(text)
        self.assertIn('"', tables["prefix"])
        self.assertNotEqual(tables["copy-mode-vi"]["V"], tables["copy-mode-vi"]["v"])
        self.assertIn("$(never-run)", tables["prefix"]["w"])

    def test_copy_mode_distinguishes_shift_and_escape_semantics(self):
        groups = shortcuts.reference("", category="Copy mode", tmux_tables=shortcuts.DEFAULT_TMUX)
        rows = {row["label"]: row for group in groups for row in group["rows"]}
        self.assertEqual(rows["Select whole line"]["keys"], ["Shift+V"])
        self.assertEqual(rows["Toggle rectangular selection"]["keys"], ["V"])
        self.assertEqual(rows["Clear selection"]["keys"], ["Esc"])
        self.assertEqual(rows["Exit copy mode"]["keys"], ["Q"])

    def test_live_tmux_overrides_do_not_advertise_removed_or_reassigned_keys(self):
        tables = {"prefix": {"n": "next-window", "w": "run-shell echo something-else"}}
        groups = shortcuts.reference("", category="tmux", tmux_tables=tables)
        labels = [row["label"] for group in groups for row in group["rows"]]
        self.assertEqual(labels, ["Next window"])

    def test_resize_mode_is_scoped_to_advanced_and_requires_an_entry_binding(self):
        text = '''bindsym $mod+r mode "resize"
mode "resize" {
 bindsym Left resize shrink width 10 px
 bindsym Down resize shrink height 10 px
 bindsym Up resize grow height 10 px
 bindsym Right resize grow width 10 px
 bindsym Return mode "default"
 bindsym Escape mode "default"
}
'''
        groups = shortcuts.reference(text, category="Advanced")
        self.assertEqual([row["label"] for group in groups for row in group["rows"]], ["Resize window", "Finish resizing"])
        self.assertEqual(shortcuts.reference(text.split('\n', 1)[1], category="Advanced"), [])

    def test_arrow_aliases_are_shown_only_when_they_match(self):
        text = "\n".join(f"bindsym $mod+{key} focus {direction}" for key, direction in
                         zip(["h", "j", "k", "l", "Left", "Down", "Up", "Right"],
                             ["left", "down", "up", "right"] * 2))
        row = shortcuts.reference(text)[0]["rows"][0]
        self.assertTrue(row["arrows"])
        self.assertFalse(shortcuts.reference(text.replace("$mod+Up focus up", "$mod+Up exec other"))[0]["rows"][0]["arrows"])

    def test_super_search_still_works_with_mac_labels(self):
        groups = shortcuts.reference("bindsym $mod+Return exec terminal", "super", "mac")
        self.assertEqual(groups[0]["rows"][0]["keys"], ["⌘", "Enter"])

    def test_application_search_uses_slash_keycap_in_both_keyboard_contexts(self):
        text = "bindsym --release $mod+Shift+slash exec xps-command-search\n"
        for keyboard, modifier in [("xps", "Super"), ("mac", "⌘")]:
            groups = shortcuts.reference(text, "application command", keyboard)
            row = groups[0]["rows"][0]
            self.assertEqual(row["label"], "Application command search")
            self.assertEqual(row["keys"], [modifier, "Shift", "/"])

    def test_tmux_snapshot_only_issues_read_commands_and_handles_stopped_server(self):
        results = [SimpleNamespace(returncode=0, stdout="bind-key -T prefix c new-window\n"),
                   SimpleNamespace(returncode=0, stdout="bind-key -T copy-mode-vi Space send-keys -X begin-selection\n")]
        with patch.object(shortcuts.subprocess, "run", side_effect=results) as run:
            tables, status = shortcuts.load_tmux("/pinned/tmux")
        self.assertEqual([call.args[0] for call in run.call_args_list],
                         [["/pinned/tmux", "list-keys", "-T", "prefix"],
                          ["/pinned/tmux", "list-keys", "-T", "copy-mode-vi"]])
        self.assertEqual(tables["prefix"]["c"], "new-window")
        with patch.object(shortcuts.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            tables, status = shortcuts.load_tmux("/pinned/tmux")
        self.assertEqual(tables, shortcuts.DEFAULT_TMUX)
        self.assertIn("stopped", status)


if __name__ == "__main__":
    unittest.main()
