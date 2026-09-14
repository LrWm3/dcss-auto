# Terminal play with browser spectators

Open http://127.0.0.1:8082/ and click a running player's name. No login is
needed to spectate. Each browser watches the same game that the agent controls
through its terminal. Browser spectators cannot send gameplay input.

The ready-to-use game is http://127.0.0.1:8082/#watch-AgentWatch . It is a
Minotaur Fighter on Dungeon:1, waiting for input in tmux session
`dcss-agent-watch`. No autonomous player is attached to that session yet.

## Commands for the agent

From `/home/reeldata/wk/exp/dcss`, start a game in a terminal/PTY:

```bash
./play-webtiles.sh MyAgent
```

This is normal terminal Crawl: read its terminal output and send the usual
Crawl keys. When using an execution tool, enable `tty: true`. Extra Crawl
arguments can follow the player name. Use a distinct name for each game.

Alternatively, control the already-running example through tmux:

```bash
tmux capture-pane -pt dcss-agent-watch
tmux send-keys -t dcss-agent-watch -l 'l'
tmux send-keys -t dcss-agent-watch Escape
```

Send commands in small batches and read the result before continuing. A human
can attach with `tmux attach -t dcss-agent-watch`; detach using Ctrl-b then d.
Coordinate with the agent before taking over input. Crawl waits whenever no
one sends keys, so pausing the agent also pauses play.

For a separate persistent game:

```bash
tmux new-session -d -s my-crawl -x 100 -y 32 /home/reeldata/wk/exp/dcss/play-webtiles.sh MyAgent
```

To continue a character from the old console build, first have its controlling
agent save and exit that game, then launch `./play-webtiles.sh CHARACTER`.
The launcher uses the same source working directory and default save location.
Do not run two processes against the same character save. Existing console
processes do not acquire a WebTiles socket until relaunched this way.

## Server

The server is running in tmux session `dcss-webtiles-server`. View its log with:

```bash
tmux capture-pane -pt dcss-webtiles-server
```

If it is stopped, start it with `./start-webtiles.sh`, or start that command in
a detached tmux session. Do not launch a second server on the same port.
After a server restart, refresh your browser; running terminal games are
rediscovered automatically. Terminal play can continue with no server attached.

For a phone or another machine connected to Tailscale, open
http://100.66.216.105:8082/#watch-AgentWatch directly. The server listens on
localhost and this machine's private Tailscale IPv4 address, not on its LAN
or public address. This does not require SSH or Tailscale Serve.

Alternatively, forward the localhost port over SSH:

```bash
ssh -N -L 8082:127.0.0.1:8082 user@crawl-machine
```

Then open http://127.0.0.1:8082/ on that machine. A terminal player can also
SSH into the Crawl machine and run the launcher or attach to tmux there.

## Implementation

`crawl-webtiles` supports both curses terminal output and WebTiles. The
launcher supplies `-webtiles-socket`; the server uses `watch_socket_dirs` to
attach as a spectator (`primary: false`). Socket files live in
`.webtiles/sockets`. The server configuration is in
`crawl-0.35/crawl-ref/source/webserver/config.yml`. A small change to the
server's socket watcher also discovers games already running at startup.

Verified locally: terminal character creation and a turn updated WebTiles;
a spectator keypress did not advance the game; restarting the server and
refreshing reattached to the same game and turn.
