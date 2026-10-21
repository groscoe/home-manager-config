function __groscoe_backward_kill_fragment -d "Kill the commandline fragment before the cursor"
  set -l buffer (commandline -b)
  set -l cursor (commandline -C)
  set -l before (string sub -s 1 -l $cursor -- "$buffer")

  if test -z "$before"
    return
  end

  set -l fragment (string match -r '[[:space:]]+$' -- "$before")

  if test -z "$fragment"
    set fragment (string match -r '[^[:space:]/._:=@,+-]+$' -- "$before")
  end

  if test -z "$fragment"
    set fragment (string match -r '[/._:=@,+-]+$' -- "$before")
  end

  set -l fragment_length (string length -- "$fragment")
  set -l new_cursor (math $cursor - $fragment_length)
  set -l kept (string sub -s 1 -l $new_cursor -- "$buffer")
  set -l after (string sub -s (math $cursor + 1) -- "$buffer")

  commandline -r -- "$kept$after"
  commandline -C $new_cursor
end

bind \e\x7f __groscoe_backward_kill_fragment
bind \e\b __groscoe_backward_kill_fragment

if bind -M insert > /dev/null 2>&1
  bind -M insert \e\x7f __groscoe_backward_kill_fragment
  bind -M insert \e\b __groscoe_backward_kill_fragment
end
