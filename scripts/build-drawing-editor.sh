#!/bin/sh
# Rebuild the Excalidraw page the app embeds (notterizmus/drawing_web) from web/drawing.
# Needed only after changing web/drawing or its Excalidraw version: the built files are
# committed, because the Debian and snap builds have no network. Needs Node.js and npm.
set -eu
cd "$(dirname "$0")/.."
src=web/drawing
out=notterizmus/drawing_web

(cd "$src" && npm ci --no-audit --no-fund)
rm -rf "$out"
mkdir -p "$out"
(cd "$src" && node_modules/.bin/esbuild main.jsx --bundle --format=esm --splitting --minify \
    --target=safari16 --conditions=production --legal-comments=none --define:process.env.NODE_ENV='"production"' \
    --define:process.env.IS_PREACT='"false"' \
    --alias:@excalidraw/mermaid-to-excalidraw=./mermaid-stub.js \
    --loader:.woff2=file --chunk-names='chunk-[hash]' --outdir="../../$out")
cp "$src/index.html" "$src/env.js" "$out/"

# Fonts: all but the CJK one (13 MB in 200 files); such text falls back to a system font.
pkg="$src/node_modules/@excalidraw/excalidraw"
mkdir -p "$out/fonts"
for d in "$pkg"/dist/prod/fonts/*; do
    [ "$(basename "$d")" = Xiaolai ] || cp -r "$d" "$out/fonts/"
done
node -e 'console.log(require("./'"$pkg"'/package.json").version)' >"$out/VERSION"
du -sh "$out"
