# Keep the physical ABNT-2 keyboard policy independent of the connecting client.
[[ -n "${DISPLAY:-}" ]] || exit 0
setxkbmap -layout br -option caps:escape
xmodmap -e 'keycode 20 = minus underscore minus underscore backslash bar backslash'

# Preserve the existing rotated tablet area. No attached stylus is a normal case.
while IFS= read -r stylus_id; do
  xsetwacom set "$stylus_id" rotate ccw
  xsetwacom set "$stylus_id" area 0 5050 15200 14550
done < <(xsetwacom list devices | sed -nE 's/.*id: ([0-9]+).*STYLUS.*/\1/p')
