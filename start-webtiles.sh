#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
crawl_root="$workspace_root/crawl-0.35/crawl-ref/source"
python_bin="$workspace_root/.build-venv/bin/python"

if [[ ! -x "$crawl_root/crawl-webtiles" ]]; then
    echo "Missing WebTiles binary: $crawl_root/crawl-webtiles" >&2
    echo "Build it with: make -C $crawl_root WEBTILES=y" >&2
    exit 1
fi

mkdir -p "$workspace_root/.webtiles/"{sockets,rcs,running,ttyrecs}
cd "$crawl_root"
exec "$python_bin" webserver/server.py "$@"
