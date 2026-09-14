#!/usr/bin/env bash
# Send one tmux key to our character, then observe; no automatic combat loop.
set -euo pipefail
if (( $# > 1 )); then
    echo 'Usage: bash crawl-step.sh [tmux-key]' >&2
    exit 2
fi
if (( $# == 1 )); then
    tmux send-keys -t codex-mibe -- "$1"
    sleep 0.15
fi
tmux capture-pane -pt codex-mibe
tmux capture-pane -pt codex-mibe | perl -CSD -e '
    my @rows = <STDIN>;
    for my $y (1 .. $#rows-1) {
        my $x = index(substr($rows[$y], 0, 33), "@");
        next unless $x > 0;
        print "Adjacent tiles (NW N NE / W @ E / SW S SE):\n";
        for my $r ($y-1 .. $y+1) {
            print substr($rows[$r], $x-1, 3), "\n";
        }
    }'
