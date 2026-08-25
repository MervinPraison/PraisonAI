/**
 * The release pipeline has three moving parts that must agree, and none of
 * them fails loudly when they do not:
 *
 *   - the workflow matrix, which decides what gets built
 *   - tauri.conf.json's bundle targets, which decide what the bundler will
 *     actually emit -- given a target it does not know, it writes nothing and
 *     still exits zero
 *   - INSTALL.md, which tells people the filename to download
 *
 * A release that quietly ships three platforms instead of four is worse than
 * one that fails, because nobody notices. These are cheap string checks, but
 * each one stands for a way a release has already gone out empty.
 */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';

const root = new URL('../../../../', import.meta.url);
const workflow = readFileSync(new URL('.github/workflows/desktop-release.yml', root), 'utf8');
const config = JSON.parse(
  readFileSync(new URL('src/praisonai-desktop/src-tauri/tauri.conf.json', root), 'utf8'));
const install = readFileSync(new URL('src/praisonai-desktop/INSTALL.md', root), 'utf8');

/** The matrix legs, as (bundles, asset, ext) triples. */
function legs() {
  const found = [];
  const re = /-\s*runner:[\s\S]*?asset:\s*([\w-]+)/g;
  for (const block of workflow.split(/-\s+runner:/).slice(1)) {
    const bundles = /bundles:\s*(\S+)/.exec(block);
    const asset = /asset:\s*(\S+)/.exec(block);
    const ext = /ext:\s*(\S+)/.exec(block);
    if (bundles && asset && ext) {
      found.push({ bundles: bundles[1], asset: asset[1], ext: ext[1] });
    }
  }
  void re;
  return found;
}

test('every platform anyone can run this on is built', () => {
  const assets = legs().map((l) => l.asset);
  for (const required of ['macos-apple-silicon', 'macos-intel', 'windows-x64-setup', 'linux-x64']) {
    assert.ok(assets.includes(required), `the release does not build ${required}: ${assets}`);
  }
});

test('every bundle the workflow asks for is one the config declares', () => {
  // The bundler exits zero after writing nothing when handed a target it does
  // not know, so this mismatch produces a green build with no artifacts.
  const declared = config.bundle.targets;
  for (const { bundles, asset } of legs()) {
    for (const bundle of bundles.split(',')) {
      assert.ok(declared.includes(bundle),
                `${asset} builds "${bundle}", which tauri.conf.json does not list: ${declared}`);
    }
  }
});

test('the config still declares the macOS targets it always had', () => {
  for (const bundle of ['app', 'dmg']) {
    assert.ok(config.bundle.targets.includes(bundle), `lost the ${bundle} target`);
  }
});

test('an icon exists for every platform that needs a distinct format', () => {
  const icons = config.bundle.icon.join(' ');
  // Windows is the one that fails hardest: tauri-build does not warn about a
  // missing .ico, it refuses to compile at all.
  assert.match(icons, /\.ico/, 'no Windows icon; the Windows build cannot compile');
  assert.match(icons, /\.icns/, 'no macOS icon');
  assert.match(icons, /\.png/, 'no PNG set; Linux installs those into hicolor');
});

test('the install instructions name the filenames the workflow produces', () => {
  for (const { asset, ext } of legs()) {
    assert.ok(install.includes(`${asset}.${ext}`),
              `INSTALL.md never mentions ${asset}.${ext}, so nobody knows to download it`);
  }
});

test('the completeness check covers exactly what the matrix builds', () => {
  // The verify job is the backstop for a silently-missing platform; if it
  // checks a different list than the matrix builds, it is theatre.
  const checked = /for want in ([^\n;]+); do/.exec(workflow);
  assert.ok(checked, 'the release no longer verifies that assets were attached');
  const names = checked[1].trim().split(/\s+/);
  assert.deepEqual(names.sort(), legs().map((l) => l.asset).sort());
});

test('a build that produces no bundle fails instead of uploading nothing', () => {
  // The original failure this pipeline exists for was a release with zero
  // assets. Exiting zero on an empty bundle directory recreates it exactly.
  //
  // Scoped to the naming step rather than grepping the whole file: `exit 1`
  // appears in the verify job too, so a file-wide search passed even with this
  // step's guard removed.
  const start = workflow.indexOf('Name the artifact for the platform');
  assert.notEqual(start, -1, 'the artifact-naming step is gone');
  const step = workflow.slice(start, workflow.indexOf('Attach it to the release'));
  assert.match(step, /if \[ -z "\$found" \]/, 'nothing checks whether a bundle was produced');
  assert.match(step, /exit 1/, 'an empty bundle directory does not fail the job');
});

test('the Linux leg installs the webkit and tray libraries the app links against', () => {
  const linux = workflow.slice(workflow.indexOf('Install the Linux build dependencies'));
  for (const pkg of ['libwebkit2gtk-4.1-dev', 'libappindicator3-dev', 'librsvg2-dev']) {
    assert.ok(linux.includes(pkg), `Linux build is missing ${pkg}`);
  }
  assert.ok(!linux.includes('libayatana-appindicator3-dev'),
            'mixing ayatana and libappindicator changes the .deb\'s generated Depends');
});

test('the Linux build host is old enough for the glibc floor it promises', () => {
  // glibc is forward-compatible only: the build host decides the oldest
  // distribution the .deb can start on, and no runtime flag can widen it.
  assert.match(workflow, /runner:\s*ubuntu-22\.04/,
               'building Linux on a newer image silently drops older distributions');
  assert.ok(install.includes('22.04'), 'INSTALL.md does not say which distributions are supported');
});
