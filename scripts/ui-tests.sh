#!/bin/sh
# Run the GTK UI tests (tests/ui) on a private display: no window appears on your
# screen, and your own settings and notes are never touched. Fails if any test fails
# or GTK prints a warning. Extra arguments go to unittest, e.g. -v or -k cursor.
#
# Uses GTK's Broadway server (package libgtk-4-bin). The tests connect a small client to
# it (tests/ui/broadway_input.py) that presses real keys, drags the mouse and answers
# frame roundtrips, so frames run at full speed. NOTTERIZMUS_UI_BACKEND=weston runs on a
# headless Weston instead (no real keyboard or mouse input there; those tests are skipped).
set -eu
cd "$(dirname "$0")/.."

tmp=$(mktemp -d "${TMPDIR:-/tmp}/notterizmus-ui.XXXXXX")
spid=
tpid=
cleanup() {
    [ -n "$tpid" ] && kill "$tpid" 2>/dev/null
    [ -n "$spid" ] && kill "$spid" 2>/dev/null
    rm -rf "$tmp"
}
trap cleanup EXIT
trap 'exit 130' INT TERM
rundir=${XDG_RUNTIME_DIR:-/tmp}

wait_for() {  # wait up to 5 s for a socket
    i=0
    while [ ! -S "$1" ] && [ "$i" -lt 50 ]; do sleep 0.1; i=$((i + 1)); done
    [ -S "$1" ] || { echo "display server didn't start; its log:" >&2; cat "$tmp/server.log" >&2; exit 2; }
}

if [ "${NOTTERIZMUS_UI_BACKEND:-}" = weston ]; then
    command -v weston >/dev/null || { echo "weston not found (sudo apt install weston)" >&2; exit 2; }
    sock="notterizmus-ui-$$"
    weston --backend=headless --socket="$sock" --width=1280 --height=900 --idle-time=0 \
        >"$tmp/server.log" 2>&1 &
    spid=$!
    wait_for "$rundir/$sock"
    # No GPU on a headless display: skip GTK's GL/Vulkan probing (and its libEGL noise)
    display="GDK_BACKEND=wayland WAYLAND_DISPLAY=$sock GDK_DISABLE=gl,vulkan NOTTERIZMUS_UI_FRAMES=1"
    echo "UI tests on a headless Weston"
elif command -v gtk4-broadwayd >/dev/null; then
    n=60  # a free Broadway display; its socket is broadway<n+1>.socket
    while [ -e "$rundir/broadway$((n + 1)).socket" ] && [ "$n" -lt 99 ]; do n=$((n + 1)); done
    gtk4-broadwayd --address 127.0.0.1 --port $((18000 + n)) ":$n" >"$tmp/server.log" 2>&1 &
    spid=$!
    wait_for "$rundir/broadway$((n + 1)).socket"
    display="GDK_BACKEND=broadway BROADWAY_DISPLAY=:$n NOTTERIZMUS_UI_BROADWAY_PORT=$((18000 + n)) NOTTERIZMUS_UI_FRAMES=1"
    echo "UI tests on Broadway, with real keyboard and mouse input"
else
    echo "Needs gtk4-broadwayd: sudo apt install libgtk-4-bin" >&2
    exit 2
fi

mkdir -p "$tmp/config" "$tmp/data" "$tmp/Documents"
printf 'XDG_DOCUMENTS_DIR="%s/Documents"\n' "$tmp" >"$tmp/config/user-dirs.dirs"

status=0
# shellcheck disable=SC2086  # $display is a list of VAR=value words
env -u WAYLAND_DISPLAY -u DISPLAY $display GSETTINGS_BACKEND=memory \
    XDG_CONFIG_HOME="$tmp/config" XDG_DATA_HOME="$tmp/data" \
    NOTTERIZMUS_UI_TESTS=1 NOTTERIZMUS_UI_SCRATCH="$tmp" \
    timeout 600 python3 -W default -W ignore::DeprecationWarning:gi.events \
    -W 'ignore:GLib.unix_signal_add_full:DeprecationWarning' \
    -m unittest discover -s tests/ui -t . "$@" >"$tmp/out.log" 2>&1 &
tpid=$!
wait "$tpid" || status=$?
tpid=
cat "$tmp/out.log"

if grep -E -- '-(WARNING|CRITICAL) \*\*' "$tmp/out.log" >"$tmp/warnings.log"; then
    echo "" >&2
    echo "GTK printed $(wc -l <"$tmp/warnings.log") warning(s) during the UI tests:" >&2
    sed -E 's/^\([^)]*\): //; s/[0-9]{2}:[0-9]{2}:[0-9.]+: //; s/0x[0-9a-f]+/0x…/g' "$tmp/warnings.log" \
        | sort | uniq -c | head -n 20 >&2
    [ "$status" -eq 0 ] && status=1
fi
exit "$status"
