// Generates PWA icons from public/anvisutra-logo.svg.
// Run via: docker run --rm -v "$(pwd):/work" -w /work node:22-alpine sh -c \
//   "npm install --no-save --silent sharp && node scripts/generate-icons.mjs"

import sharp from "sharp";
import { writeFileSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(process.cwd(), "public");
const SVG = resolve(root, "anvisutra-logo.svg");
const BG = "#0A1A1F"; // matches the SVG background — dark navy/teal

async function rasterize(size, outName, { background = null, padPct = 0 } = {}) {
  const inset = Math.round(size * padPct);
  const inner = size - inset * 2;
  let img = sharp(SVG).resize(inner, inner, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } });
  if (inset > 0 || background) {
    img = sharp({
      create: {
        width: size,
        height: size,
        channels: 4,
        background: background ?? { r: 0, g: 0, b: 0, alpha: 0 },
      },
    }).composite([
      { input: await img.png().toBuffer(), top: inset, left: inset },
    ]);
  }
  await img.png().toFile(resolve(root, outName));
  console.log("wrote", outName, size);
}

async function main() {
  // Standard "any" purpose icons — full bleed, transparent background OK.
  await rasterize(192, "icon-192.png");
  await rasterize(512, "icon-512.png");

  // Maskable icon — Android adaptive icons crop into a circle/squircle.
  // Keep logo within the central 80% of canvas (10% pad each side).
  await rasterize(512, "icon-512-maskable.png", { background: BG, padPct: 0.1 });

  // Apple touch icon — 180x180, NO transparency, dark navy bg.
  await rasterize(180, "apple-touch-icon.png", { background: BG, padPct: 0.07 });

  // Favicon: 16/32/48 PNGs combined into multi-size .ico (handwritten ICO header).
  const sizes = [16, 32, 48];
  const buffers = await Promise.all(
    sizes.map((s) =>
      sharp(SVG)
        .resize(s, s, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } })
        .png()
        .toBuffer(),
    ),
  );
  writeFileSync(resolve(root, "favicon.ico"), buildIco(sizes, buffers));
  console.log("wrote favicon.ico");
}

function buildIco(sizes, pngBuffers) {
  // ICO with embedded PNG entries (supported by all modern browsers).
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type 1 = icon
  header.writeUInt16LE(sizes.length, 4);

  const dir = Buffer.alloc(16 * sizes.length);
  let offset = 6 + dir.length;
  const dataChunks = [];
  for (let i = 0; i < sizes.length; i++) {
    const size = sizes[i];
    const buf = pngBuffers[i];
    const e = i * 16;
    dir.writeUInt8(size === 256 ? 0 : size, e + 0);   // width  (0 = 256)
    dir.writeUInt8(size === 256 ? 0 : size, e + 1);   // height
    dir.writeUInt8(0, e + 2);                          // colors
    dir.writeUInt8(0, e + 3);                          // reserved
    dir.writeUInt16LE(1, e + 4);                       // planes
    dir.writeUInt16LE(32, e + 6);                      // bpp
    dir.writeUInt32LE(buf.length, e + 8);              // image size
    dir.writeUInt32LE(offset, e + 12);                 // offset
    offset += buf.length;
    dataChunks.push(buf);
  }
  return Buffer.concat([header, dir, ...dataChunks]);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
