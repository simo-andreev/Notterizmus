#!/usr/bin/env bash
# Launch Notterizmus from this checkout.
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m notterizmus "$@"
