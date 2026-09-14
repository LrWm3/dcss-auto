#!/usr/bin/env bash
# Normal terminal Crawl with a socket for browser spectators.
set -euo pipefail
workspace_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
crawl_root="$workspace_root/crawl-0.35/crawl-ref/source"
player="${1:-AgentWatch}"
if [[ $# -gt 0 ]]; then shift; fi
if [[ ! "$player" =~ ^[A-Za-z0-9]{1,20}$ ]]; then
    echo "Player name must contain 1–20 letters or digits." >&2
    exit 1
fi
mkdir -p "$workspace_root/.webtiles/sockets"
socket_path="$workspace_root/.webtiles/sockets/$player:terminal.sock"
if [[ -e "$socket_path" ]]; then
    echo "A game socket already exists for $player: $socket_path" >&2
    echo "Use another name, or reconnect to the existing terminal session." >&2
    exit 1
fi
if [[ ! -t 0 || ! -t 1 ]]; then
    echo "Run this in a terminal, tmux, or a tool with PTY/tty enabled." >&2
    exit 1
fi
cd "$crawl_root"
exec ./crawl-webtiles -name "$player" -webtiles-socket "$socket_path" "$@"
