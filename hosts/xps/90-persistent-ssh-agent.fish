# Mosh outlives its bootstrap SSH connection and any forwarded agent socket.
# Preserve a working forwarded agent; repair missing sockets using the local agent.
function __xps_persistent_ssh_agent --on-event fish_preexec
    if set -q SSH_AUTH_SOCK; and test -S "$SSH_AUTH_SOCK"
        return
    end
    if set -q XDG_RUNTIME_DIR; and test -S "$XDG_RUNTIME_DIR/ssh-agent"
        set -gx SSH_AUTH_SOCK "$XDG_RUNTIME_DIR/ssh-agent"
    end
end

__xps_persistent_ssh_agent
