#!/usr/bin/env bash
# Explicit, observation-first controller for a Crawl terminal session.
#
# Examples:
#   ./crawl-control.sh --session codex-next
#   ./crawl-control.sh --session codex-next --keys o
#   ./crawl-control.sh --session codex-next --keys k k k
#   ./crawl-control.sh --session codex-next --text 'short note'
set -euo pipefail

usage() {
    sed -n '2,10p' "$0"
    cat >&2 <<'EOF'

Options:
  -s, --session NAME   tmux session to control (required)
  -w, --wait SECONDS   delay after input (default: 0.20)
  -n, --lines NUMBER   number of recent pane lines (default: 80)
      --keys K...      send named tmux keys, e.g. Escape, Enter, k, >
      --text TEXT       type TEXT literally (use for annotations/searches)
  -h, --help           show this help

With no --keys or --text, the command is read-only and only captures the pane.
EOF
}

session=''
wait_seconds='0.20'
lines='80'
key_args=()
text_arg=''
send_mode=''

while (($#)); do
    case "$1" in
        -s|--session)
            (($# >= 2)) || { echo "Missing value for $1" >&2; exit 2; }
            session=$2
            shift 2
            ;;
        -w|--wait)
            (($# >= 2)) || { echo "Missing value for $1" >&2; exit 2; }
            wait_seconds=$2
            shift 2
            ;;
        -n|--lines)
            (($# >= 2)) || { echo "Missing value for $1" >&2; exit 2; }
            lines=$2
            shift 2
            ;;
        --keys)
            shift
            (($#)) || { echo "--keys needs at least one key" >&2; exit 2; }
            [[ -z "$send_mode" ]] || { echo "Choose --keys or --text, not both" >&2; exit 2; }
            send_mode='keys'
            while (($#)) && [[ "$1" != -* ]]; do
                key_args+=("$1")
                shift
            done
            ((${#key_args[@]})) || { echo "--keys needs at least one key" >&2; exit 2; }
            ;;
        --text)
            (($# >= 2)) || { echo "Missing value for --text" >&2; exit 2; }
            [[ -z "$send_mode" ]] || { echo "Choose --keys or --text, not both" >&2; exit 2; }
            send_mode='text'
            text_arg=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option or key: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[[ -n "$session" ]] || { echo "An explicit --session is required." >&2; exit 2; }
[[ "$lines" =~ ^[1-9][0-9]*$ ]] || { echo "--lines must be a positive integer." >&2; exit 2; }
[[ "$wait_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "--wait must be a non-negative number." >&2; exit 2; }

if ! tmux has-session -t "$session" 2>/dev/null; then
    echo "No tmux session named '$session'. Refusing to send input." >&2
    exit 1
fi

case "$send_mode" in
    keys)
        tmux send-keys -t "$session" "${key_args[@]}"
        sleep "$wait_seconds"
        ;;
    text)
        tmux send-keys -t "$session" -l "$text_arg"
        sleep "$wait_seconds"
        ;;
esac

pane=$(tmux capture-pane -p -t "$session" -S "-$lines")
printf '%s\n' "$pane"

# Print a compact local view around @ to make movement checks quicker.
printf '%s\n' "$pane" | perl -CSD -e '
    my @rows = <STDIN>;
    for my $y (1 .. $#rows - 1) {
        my $x = index(substr($rows[$y], 0, 33), "@");
        next unless $x > 0;
        print "Adjacent tiles (NW N NE / W @ E / SW S SE):\n";
        for my $r ($y-1 .. $y+1) {
            print substr($rows[$r], $x-1, 3), "\n";
        }
        last;
    }
'
