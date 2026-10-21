# Tmux clipboard on xps

From an SSH terminal, enter copy mode with `; [` and select as usual (`Space`,
then movement keys). Press `y` or `Enter` to copy to the connecting terminal's
clipboard. Paste into a Mac application with Command-V. Mouse drag-and-release
also copies. `; w` sends the latest tmux buffer to that terminal again, without
making another selection. The usual tmux `prefix ]` paste still works.

On the physical xps keyboard the prefix remains `ç`, and copies go to the xps
desktop clipboard. Routing comes from the initiating client's process environment,
so local and SSH clients can use the same tmux session. Selection bytes go through
stdin; they are never evaluated as shell commands or interpolated as tmux formats.

The SSH route uses tmux's targeted OSC 52 output over the existing connection.
The terminal must support clipboard writes; in iTerm2, enable Settings → General →
Selection → Applications in terminal may access clipboard. This was already
enabled on mbp when installed. There is no fixed Mac address or reverse SSH login.
Other clients need a terminal supporting OSC 52. Mosh 1.4 requires an explicit
`c` selector, supplied by the terminal capability override in `clipboard.conf`.
An already attached tmux client must detach and reattach after changing that
capability; restarting the server or its sessions is unnecessary. Nested tmux
requires clipboard support in its outer layer as well.

`clipboard.conf` loads after TPM so the old tmux-yank selection bindings cannot
replace it. Native automatic clipboard broadcasts are disabled; the helper sends
OSC 52 only to the initiating client. The helper uses X11 for physical clients
because the installed VTE/Guake does not provide OSC 52 clipboard writes.
