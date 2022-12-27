# Setup fzf
# ---------
if [[ ! "$PATH" == */usr/bin* ]]; then
  export PATH="$PATH:/usr/bin"
fi

# Auto-completion
# ---------------
[[ $- == *i* ]] && source "/usr/share/fzf/completion.bash" 2> /dev/null

# Key bindings
# ------------
source "/usr/share/fzf/key-bindings.bash"

#
# Custom bindings below
#

export FZF_CTRL_T_OPTS="--layout=reverse --bind='ctrl-t:toggle-preview' --preview='/home/groscoe/Projects/preview.sh {}' --height=100%"
