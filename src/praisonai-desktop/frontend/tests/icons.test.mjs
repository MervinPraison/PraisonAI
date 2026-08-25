/**
 * The icons, and the one property that decides whether they render.
 *
 * The menubar showed a solid white block for a whole build. A macOS template
 * image is drawn from its ALPHA CHANNEL ALONE -- the system discards the colour
 * and tints the shape -- and the tray was handed the app icon, whose alpha is
 * opaque edge to edge. There was nothing wrong with how it looked as a file;
 * it was the wrong kind of file for the job.
 *
 * These read the PNG headers directly rather than pulling in an image library:
 * width, height, colour type and the IHDR are all at fixed offsets, and the
 * alpha histogram comes from decompressing IDAT.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { inflateSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const ICONS = fileURLToPath(new URL('../../src-tauri/icons/', import.meta.url));

/** Parse a PNG far enough to read its pixels. Only what these tests need. */
function readPng(name) {
  const buf = readFileSync(ICONS + name);
  assert.equal(buf.readUInt32BE(0), 0x89504e47, `${name} is not a PNG`);
  const width = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  const bitDepth = buf[24];
  const colourType = buf[25];

  const idat = [];
  let off = 8;
  while (off < buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString('ascii', off + 4, off + 8);
    if (type === 'IDAT') idat.push(buf.subarray(off + 8, off + 8 + len));
    off += len + 12;
    if (type === 'IEND') break;
  }
  return { width, height, bitDepth, colourType, raw: inflateSync(Buffer.concat(idat)) };
}

/** Alpha of every pixel of an 8-bit RGBA PNG, undoing the per-row filter. */
function alphaChannel(png) {
  assert.equal(png.colourType, 6, 'expected RGBA');
  assert.equal(png.bitDepth, 8);
  const bpp = 4;
  const stride = png.width * bpp;
  const out = [];
  const prev = Buffer.alloc(stride);
  let cur = Buffer.alloc(stride);
  let p = 0;
  for (let y = 0; y < png.height; y++) {
    const filter = png.raw[p++];
    png.raw.copy(cur, 0, p, p + stride);
    p += stride;
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? cur[i - bpp] : 0;
      const b = prev[i];
      const c = i >= bpp ? prev[i - bpp] : 0;
      let v = cur[i];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) {
        const pp = a + b - c;
        const pa = Math.abs(pp - a), pb = Math.abs(pp - b), pc = Math.abs(pp - c);
        v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      cur[i] = v & 0xff;
    }
    for (let x = 3; x < stride; x += bpp) out.push(cur[x]);
    cur.copy(prev);
    cur = Buffer.alloc(stride);
  }
  return out;
}

test('both icons are RGBA', () => {
  // Tauri rejects an RGB icon outright -- an earlier build shipped one and the
  // window came up with no icon at all.
  for (const name of ['icon.png', 'tray.png']) {
    assert.equal(readPng(name).colourType, 6, `${name} is not RGBA (colour type 6)`);
  }
});

test('the tray glyph lives in the alpha channel', () => {
  // The defect this file exists for. A template image whose alpha is opaque
  // everywhere renders as a filled block, whatever its colours look like.
  const png = readPng('tray.png');
  const alpha = alphaChannel(png);
  const clear = alpha.filter((v) => v < 8).length;
  const solid = alpha.filter((v) => v > 247).length;
  assert.ok(clear > alpha.length * 0.3,
    `only ${clear}/${alpha.length} pixels are transparent -- this is a block, not a glyph`);
  assert.ok(solid > alpha.length * 0.1,
    `only ${solid}/${alpha.length} pixels are opaque -- there is no mark to see`);
});

test('the tray glyph is sized for a Retina menubar', () => {
  const png = readPng('tray.png');
  assert.equal(png.width, 44, 'the menubar is 22pt; a template needs 44px for 2x');
  assert.equal(png.height, 44);
});

test('the tray glyph is inset, not bleeding to the edge', () => {
  // A menubar icon that touches its own bounds collides with its neighbours.
  const png = readPng('tray.png');
  const alpha = alphaChannel(png);
  const at = (x, y) => alpha[y * png.width + x];
  for (let i = 0; i < png.width; i++) {
    assert.equal(at(i, 0), 0, `row 0 has ink at x=${i}`);
    assert.equal(at(i, png.height - 1), 0, `last row has ink at x=${i}`);
    assert.equal(at(0, i), 0, `column 0 has ink at y=${i}`);
    assert.equal(at(png.width - 1, i), 0, `last column has ink at y=${i}`);
  }
});

test('the app icon is inset within its canvas, per the macOS icon grid', () => {
  // Artwork drawn edge to edge looks oversized beside every system app in the
  // dock. Apple's grid puts a rounded square at ~82% of the canvas.
  const png = readPng('icon.png');
  const alpha = alphaChannel(png);
  const at = (x, y) => alpha[y * png.width + x];
  const mid = Math.floor(png.height / 2);
  let left = 0;
  while (left < png.width && at(left, mid) < 8) left++;
  const inset = left / png.width;
  assert.ok(inset > 0.05 && inset < 0.15,
    `artwork starts ${(inset * 100).toFixed(1)}% in; expected roughly 9%`);
  assert.ok(at(Math.floor(png.width / 2), mid) > 247, 'the middle of the icon is transparent');
});
