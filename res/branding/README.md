# Sasthotech branding assets

`sasthotech-logo.png` is the canonical supplied logo. Generated desktop assets
are committed so release builds do not require ImageMagick. Regenerate on macOS
with ImageMagick and `iconutil` using the commands below.

## Step 1: Add the canonical source image

```bash
mkdir -p res/branding
cp "/path/to/Untitled design.png" res/branding/sasthotech-logo.png
```

## Step 2: Add the monochrome tray source

Create `res/branding/sasthotech-tray.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <g fill="none" stroke="#000" stroke-width="12" stroke-linecap="round">
    <path d="M31 18v28c0 23 14 38 33 38s33-15 33-38V18"/>
    <path d="M64 84v12c0 11 8 18 18 18"/>
  </g>
  <circle cx="92" cy="112" r="10" fill="#000"/>
</svg>
```

## Step 3: Generate the square master and platform files

Install the development-only generator, then run:

```bash
brew install imagemagick
magick res/branding/sasthotech-logo.png -trim +repage \
  -resize '880x880>' -gravity center -background white \
  -extent 1024x1024 /tmp/sasthotech-master.png

magick /tmp/sasthotech-master.png -define icon:auto-resize=256,128,64,48,32,16 \
  flutter/windows/runner/resources/app_icon.ico

magick /tmp/sasthotech-master.png -resize 32x32 res/32x32.png
magick /tmp/sasthotech-master.png -resize 64x64 res/64x64.png
magick /tmp/sasthotech-master.png -resize 128x128 res/128x128.png
magick /tmp/sasthotech-master.png -resize 256x256 res/128x128@2x.png
magick /tmp/sasthotech-master.png -resize 256x256 res/icon.png
magick /tmp/sasthotech-master.png -resize 1024x1024 res/mac-icon.png

rm -rf /tmp/SasthotechRemote.iconset
mkdir -p /tmp/SasthotechRemote.iconset
for size in 16 32 128 256 512; do
  magick /tmp/sasthotech-master.png -resize "${size}x${size}" \
    "/tmp/SasthotechRemote.iconset/icon_${size}x${size}.png"
  double=$((size * 2))
  magick /tmp/sasthotech-master.png -resize "${double}x${double}" \
    "/tmp/SasthotechRemote.iconset/icon_${size}x${size}@2x.png"
done
iconutil -c icns /tmp/SasthotechRemote.iconset \
  -o flutter/macos/Runner/AppIcon.icns

magick -background none res/branding/sasthotech-tray.svg -resize 44x44 \
  res/mac-tray-dark-x2.png
cp res/mac-tray-dark-x2.png res/mac-tray-light-x2.png
```

Generate `res/scalable.svg` as an SVG wrapper containing the square master:

```bash
encoded=$(base64 < /tmp/sasthotech-master.png | tr -d '\n')
printf '%s\n' \
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">' \
  "  <image width=\"1024\" height=\"1024\" href=\"data:image/png;base64,$encoded\"/>" \
  '</svg>' > res/scalable.svg
```

## Step 4: Verify image files

```bash
identify res/{32x32,64x64,128x128,128x128@2x,icon,mac-icon}.png
identify flutter/windows/runner/resources/app_icon.ico
iconutil -c iconset flutter/macos/Runner/AppIcon.icns -o /tmp/verify.iconset
test -s res/mac-tray-dark-x2.png
test -s res/scalable.svg
```
