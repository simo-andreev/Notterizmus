#!/usr/bin/env bash
# Adds Notterizmus to the GNOME app grid (per-user, no root needed).
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$DEST"
ICON_DEST="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$ICON_DEST"
cp "$HERE/data/icons/hicolor/scalable/apps/dev.simo.Notterizmus.svg" "$ICON_DEST/"
gtk-update-icon-cache -q -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null || true
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
