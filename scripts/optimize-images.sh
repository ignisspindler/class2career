#!/usr/bin/env bash
# optimize-images.sh
# Generates WebP + resized PNG srcset variants for every image in assets/
# Requires: sips (macOS built-in), cwebp (brew install webp)
#
# Output layout for each source foo.png:
#   assets/img/foo-400.webp   (small)
#   assets/img/foo-800.webp   (medium)
#   assets/img/foo-400.png    (small PNG fallback)
#   assets/img/foo-800.png    (medium PNG fallback)
#
# Usage: bash scripts/optimize-images.sh
# Run from: biztranslation/website/

set -euo pipefail

CWEBP=/opt/homebrew/bin/cwebp
SITE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COVERS_DIR="$SITE_DIR/assets/covers"
IMAGES_DIR="$SITE_DIR/assets/images"
OUT_DIR="$SITE_DIR/assets/img"

mkdir -p "$OUT_DIR"

# Image widths to generate.
# Covers display at ~252px (hero fan) and ~228px (workbook grid) — so 300 and 600 cover 1x/2x.
# Diagrams display at ~360px (grid) and ~350px (problem cards) — 400 and 750 cover 1x/2x.
COVER_WIDTHS=(300 600)
DIAGRAM_WIDTHS=(400 750)

total=0; done_count=0; skipped=0

process_image() {
  local src="$1"
  local widths=("${@:2}")
  local base
  base=$(basename "$src" .png)
  local updated=0

  for w in "${widths[@]}"; do
    local out_png="$OUT_DIR/${base}-${w}.png"
    local out_webp="$OUT_DIR/${base}-${w}.webp"

    # Skip if both already up-to-date
    if [[ -f "$out_png" && -f "$out_webp" && "$out_png" -nt "$src" && "$out_webp" -nt "$src" ]]; then
      ((skipped++)) || true
      continue
    fi

    # Get source pixel width
    local src_w
    src_w=$(sips --getProperty pixelWidth "$src" 2>/dev/null | awk '/pixelWidth/{print $2}')

    if [[ -z "$src_w" || "$src_w" -le "$w" ]]; then
      # Source is smaller than target; just copy and convert at native size
      sips -s format png "$src" --out "$out_png" --resampleWidth "$src_w" -Z "$src_w" > /dev/null 2>&1
    else
      sips -s format png "$src" --resampleWidth "$w" --out "$out_png" > /dev/null 2>&1
    fi

    # WebP from the resized PNG
    "$CWEBP" -q 82 -mt "$out_png" -o "$out_webp" > /dev/null 2>&1

    ((updated++)) || true
    echo "  ✓ ${base}-${w} (png + webp)"
  done

  ((total++)) || true
  if [[ "$updated" -gt 0 ]]; then ((done_count++)) || true; fi
}

echo "=== Optimizing cover images ==="
for f in "$COVERS_DIR"/*.png; do
  process_image "$f" "${COVER_WIDTHS[@]}"
done

echo ""
echo "=== Optimizing diagram images ==="
for f in "$IMAGES_DIR"/*.png; do
  process_image "$f" "${DIAGRAM_WIDTHS[@]}"
done

echo ""
echo "=== Done ==="
echo "  Processed : $total images"
echo "  Updated   : $done_count"
echo "  Skipped   : $skipped (already current)"
echo "  Output    : $OUT_DIR"

# Print size comparison for the first cover as a sanity check
sample_orig=$(du -sh "$COVERS_DIR/cover-01-business-foundation.png" 2>/dev/null | awk '{print $1}')
sample_webp=$(du -sh "$OUT_DIR/cover-01-business-foundation-600.webp" 2>/dev/null | awk '{print $1}')
echo ""
echo "  Size check: cover-01 original=$sample_orig → 600w webp=$sample_webp"
