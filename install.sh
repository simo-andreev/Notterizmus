#!/usr/bin/env bash
# Developer install: adds this checkout to the GNOME app grid (per-user, no root).
# Normal installs use the Debian package from the PPA instead (see README).
#   ./install.sh              add the launcher and icon
#   ./install.sh --uninstall  remove them again
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$DEST/dev.simo.Notterizmus.desktop"
    rm -f "${XDG_DATA_HOME:-$HOME/.local/share}"/icons/hicolor/*/apps/dev.simo.Notterizmus.png
    update-desktop-database "$DEST" 2>/dev/null || true
    echo "Removed the per-user launcher and icons."
    exit 0
fi
mkdir -p "$DEST"
ICON_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
for f in "$HERE"/data/icons/hicolor/*/apps/dev.simo.Notterizmus.png; do
    size_dir="$(basename "$(dirname "$(dirname "$f")")")"
    mkdir -p "$ICON_ROOT/$size_dir/apps"
    cp "$f" "$ICON_ROOT/$size_dir/apps/"
done
gtk-update-icon-cache -q -t "$ICON_ROOT" 2>/dev/null || true
cat > "$DEST/dev.simo.Notterizmus.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Notterizmus
Comment=Outline editor for TopCoding chapter notes
Exec="$HERE/notterizmus.sh" %f
Icon=dev.simo.Notterizmus
Terminal=false
Categories=Office;TextEditor;
StartupNotify=true
DESK
update-desktop-database "$DEST" 2>/dev/null || true
echo "Installed $DEST/dev.simo.Notterizmus.desktop"
