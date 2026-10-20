# Pure classification helper. No filesystem, device or process operations.
# Arguments: visible device count, current assertion failure, sticky failure.
classify_ro() {
    [ "$#" = 3 ] || { printf '%s\n' BLOCKED; return; }
    case "$1" in ''|*[!0-9]*) printf '%s\n' BLOCKED; return ;; esac
    case "$2:$3" in 0:0) ;; *) printf '%s\n' BLOCKED; return ;; esac
    if [ "$1" -eq 0 ]; then printf '%s\n' PARTIAL
    elif [ "$1" -gt 0 ]; then printf '%s\n' ENUMERATED_RO
    else printf '%s\n' BLOCKED
    fi
}
