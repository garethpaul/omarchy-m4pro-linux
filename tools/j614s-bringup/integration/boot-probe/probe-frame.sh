# Offline-testable RAM-file framing helper. No serial/device/sysfs operations.
# Arguments: validated request nonce, literal command, source file, RAM prefix.
# Parse one bounded LF-stripped request; CRLF/extra fields are rejected.
parse_request() {
    FRAME_REQUEST_ID=; FRAME_COMMAND=
    [ "$#" = 1 ] || return 1
    case "$1" in 'J614S_REQ_V1 '*) ;; *) return 1 ;; esac
    frame_request_tail=${1#J614S_REQ_V1 }
    frame_request_id=${frame_request_tail%% *}
    frame_request_command=${frame_request_tail#* }
    case "$frame_request_id" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#frame_request_id}" = 32 ] || return 1
    case "$frame_request_command" in help|status|before|after|logs|dmesg|probe) ;; *) return 1 ;; esac
    [ "$1" = "J614S_REQ_V1 $frame_request_id $frame_request_command" ] || return 1
    FRAME_REQUEST_ID=$frame_request_id; FRAME_COMMAND=$frame_request_command
    return 0
}

make_frame() {
    [ "$#" = 4 ] || return 1
    case "$1" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#1}" = 32 ] || return 1
    case "$2" in help|status|before|after|logs|dmesg|probe) ;; *) return 1 ;; esac
    # Freeze a bounded copy; concurrent appenders never alter the framed copy.
    if ! head -c 2097153 "$3" > "$4.snapshot"; then
        printf '%s\n' 'REFUSED: requested source could not be copied' > "$4.snapshot" || return 1
    fi
    frame_bytes=$(wc -c < "$4.snapshot") || return 1
    if [ "$frame_bytes" -gt 2097152 ]; then
        printf '%s\n' 'REFUSED: response exceeds the 2097152-byte bound' > "$4.snapshot" || return 1
        frame_bytes=$(wc -c < "$4.snapshot") || return 1
    fi
    frame_digest=$(sha256sum "$4.snapshot") || return 1
    frame_digest=${frame_digest%% *}
    {
        printf 'J614S_FRAME_V1 %s %s %s %s\n' "$1" "$2" "$frame_bytes" "$frame_digest" &&
        cat "$4.snapshot" &&
        printf '\nJ614S_END_V1 %s\n' "$1"
    } > "$4.frame"
}
