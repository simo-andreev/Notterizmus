#!/bin/sh
# Run the GTK UI tests (tests/ui) on a private display: no window appears on your
# screen, and your own settings and notes are never touched. Fails if any test fails,
# or if GTK or Python prints a warning. Extra arguments go to unittest, e.g. -v or
# -k cursor.
#
# Uses GTK's Broadway server (package libgtk-4-bin). The tests connect a small client to
# it (tests/ui/broadway_input.py) that presses real keys, drags the mouse and answers
# frame roundtrips, so frames run at full speed. NOTTERIZMUS_UI_BACKEND=weston runs on a
# headless Weston instead (no real keyboard or mouse input there; those tests are skipped).
#
# Everything a run uses lives in its own scratch folder, the display's sockets included
# (a private XDG_RUNTIME_DIR), so several runs can go at once and nothing is left behind.
# NOTTERIZMUS_UI_TIMEOUT (seconds, default 900) stops a run that hangs; a single test
# that hangs is stopped sooner, with a traceback of where (tests/ui/support.py).
set -eu
cd "$(dirname "$0")/.."

tmp=$(mktemp -d "${TMPDIR:-/tmp}/notterizmus-ui.XXXXXX")
run="$tmp/run"
runtmp=
# A socket's path is limited to about 100 bytes: with a deep TMPDIR, keep the sockets in /tmp.
if [ "$(printf %s "$run" | wc -c)" -gt 70 ]; then
    runtmp=$(mktemp -d /tmp/ntz-ui.XXXXXX)
    run="$runtmp"
fi
mkdir -p "$run"
chmod 700 "$run"
spid=
tpid=
cleanup() {
    [ -n "$tpid" ] && kill "$tpid" 2>/dev/null
    [ -n "$spid" ] && kill "$spid" 2>/dev/null
    rm -rf "$tmp"
    [ -n "$runtmp" ] && rm -rf "$runtmp"
    return 0
}
trap cleanup EXIT
trap 'exit 130' INT TERM

wait_for() {  # wait up to 15 s for the display server's socket
    i=0
    while [ ! -S "$1" ] && [ "$i" -lt 150 ] && kill -0 "$spid" 2>/dev/null; do sleep 0.1; i=$((i + 1)); done
    if [ ! -S "$1" ] || ! kill -0 "$spid" 2>/dev/null; then
        echo "display server didn't start; its log:" >&2
        cat "$tmp/server.log" >&2
        exit 2
    fi
}

# The session bus is found through the runtime folder unless its address is set: keep
# the real one, so only the display moves to the private folder.
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "${XDG_RUNTIME_DIR:-/nonexistent}/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi
unset DISPLAY WAYLAND_DISPLAY BROADWAY_DISPLAY
export XDG_RUNTIME_DIR="$run"

if [ "${NOTTERIZMUS_UI_BACKEND:-}" = weston ]; then
    command -v weston >/dev/null || { echo "weston not found (sudo apt install weston)" >&2; exit 2; }
    weston --backend=headless --socket=notterizmus-ui --width=1280 --height=900 --idle-time=0 \
        >"$tmp/server.log" 2>&1 &
    spid=$!
    wait_for "$run/notterizmus-ui"
    # No GPU on a headless display: skip GTK's GL/Vulkan probing (and its libEGL noise)
    export GDK_BACKEND=wayland WAYLAND_DISPLAY=notterizmus-ui GDK_DISABLE=gl,vulkan
    echo "UI tests on a headless Weston"
elif command -v gtk4-broadwayd >/dev/null; then
    # Display :0 is socket broadway1.socket; the tests' input client talks to input.socket.
    gtk4-broadwayd --unixsocket "$run/input.socket" :0 >"$tmp/server.log" 2>&1 &
    spid=$!
    wait_for "$run/broadway1.socket"
    export GDK_BACKEND=broadway BROADWAY_DISPLAY=:0 NOTTERIZMUS_UI_BROADWAY="$run/input.socket"
    echo "UI tests on Broadway, with real keyboard and mouse input"
else
    echo "Needs gtk4-broadwayd: sudo apt install libgtk-4-bin" >&2
    exit 2
fi

mkdir -p "$tmp/config" "$tmp/data" "$tmp/Documents"
printf 'XDG_DOCUMENTS_DIR="%s/Documents"\n' "$tmp" >"$tmp/config/user-dirs.dirs"

status=0
GSETTINGS_BACKEND=memory XDG_CONFIG_HOME="$tmp/config" XDG_DATA_HOME="$tmp/data" \
    NOTTERIZMUS_UI_TESTS=1 NOTTERIZMUS_UI_FRAMES=1 NOTTERIZMUS_UI_SCRATCH="$tmp" \
    timeout "${NOTTERIZMUS_UI_TIMEOUT:-900}" python3 -W default -W ignore::DeprecationWarning:gi.events \
    -W 'ignore:GLib.unix_signal_add_full:DeprecationWarning' \
    -m unittest discover -s tests/ui -t . "$@" >"$tmp/out.log" 2>&1 &
tpid=$!
wait "$tpid" || status=$?
tpid=
cat "$tmp/out.log"
if [ "$status" -eq 124 ]; then
    echo "" >&2
    echo "The UI tests were stopped after ${NOTTERIZMUS_UI_TIMEOUT:-900} s (NOTTERIZMUS_UI_TIMEOUT)." >&2
fi

# Warnings don't fail a test by themselves, so the run fails for them here: GLib's
# ("Gtk-WARNING **: ...") and Python's ("file.py:12: ResourceWarning: ...").
if grep -E -- '-(WARNING|CRITICAL) \*\*' "$tmp/out.log" >"$tmp/warnings.log"; then
    echo "" >&2
    echo "GTK printed $(wc -l <"$tmp/warnings.log") warning(s) during the UI tests:" >&2
    sed -E 's/^\([^)]*\): //; s/[0-9]{2}:[0-9]{2}:[0-9.]+: //; s/0x[0-9a-f]+/0x…/g' "$tmp/warnings.log" \
        | sort | uniq -c | head -n 20 >&2
    [ "$status" -eq 0 ] && status=1
fi
if grep -E '^[^ ]+\.py:[0-9]+: [A-Za-z]*Warning: ' "$tmp/out.log" >"$tmp/pywarnings.log"; then
    echo "" >&2
    echo "Python printed $(wc -l <"$tmp/pywarnings.log") warning(s) during the UI tests:" >&2
    sort "$tmp/pywarnings.log" | uniq -c | head -n 20 >&2
    [ "$status" -eq 0 ] && status=1
fi
exit "$status"
