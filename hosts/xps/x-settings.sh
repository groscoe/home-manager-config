# Keyboard/tablet policy comes from the selected hardware profile.
[[ -n "${DISPLAY:-}" ]] || exit 0
setxkbmap -layout @keyboardLayout@ @keyboardOptions@
@keyboardRemaps@

# No attached stylus is a normal case; a null tablet omits this block.
@tablet@
