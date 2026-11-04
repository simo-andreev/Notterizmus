#!/usr/bin/env bash
# Build Notterizmus packages from the last commit.
#   scripts/release.sh deb     build dist/notterizmus_<version>_all.deb to install and try locally
#   scripts/release.sh source  build the signed source package for Launchpad into dist/
#   scripts/release.sh ppa     build the signed source package and upload it to the PPA
set -euo pipefail
PPA="ppa:simeonandreev/ppa-library"
ROOT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$ROOT"

mode="${1:-}"
case "$mode" in
    deb|source|ppa) ;;
    *) sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac

VERSION="$(dpkg-parsechangelog -S Version)"
APPVER="$(python3 -c 'import notterizmus; print(notterizmus.VERSION)')"
if [ "$VERSION" != "$APPVER" ]; then
    echo "Version mismatch: debian/changelog says $VERSION, notterizmus/__init__.py says $APPVER." >&2
    exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
    echo "Uncommitted changes: commit first, packages are built from the last commit." >&2
    exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SRC="$WORK/notterizmus-$VERSION"
mkdir -p "$SRC" "$ROOT/dist"
git archive HEAD | tar -x -C "$SRC"
cd "$SRC"

if [ "$mode" = deb ]; then
    dpkg-buildpackage -b -us -uc
    cp "$WORK/notterizmus_${VERSION}_all.deb" "$ROOT/dist/"
    echo
    echo "Built dist/notterizmus_${VERSION}_all.deb — open it to install with App Center, or:"
    echo "  sudo apt install ./dist/notterizmus_${VERSION}_all.deb"
else
    # Signed with the GPG key whose email matches the Maintainer in debian/changelog.
    dpkg-buildpackage -S -sa -d
    cp "$WORK"/notterizmus_"$VERSION".dsc "$WORK"/notterizmus_"$VERSION".tar.* \
       "$WORK"/notterizmus_"$VERSION"_source.* "$ROOT/dist/"
    echo
    echo "Built dist/notterizmus_${VERSION}_source.changes"
    if [ "$mode" = ppa ]; then
        dput "$PPA" "$ROOT/dist/notterizmus_${VERSION}_source.changes"
        echo "Uploaded. Launchpad emails you when the build is accepted and when it finishes."
    fi
fi
