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
import { releaseVersion } from '../../tools/set-release-version.mjs';

const root = new URL('../../../../', import.meta.url);
const workflow = readFileSync(new URL('.github/workflows/desktop-release.yml', root), 'utf8');
const ci = readFileSync(new URL('.github/workflows/desktop.yml', root), 'utf8');
const config = JSON.parse(
  readFileSync(new URL('src/praisonai-desktop/src-tauri/tauri.conf.json', root), 'utf8'));
const install = readFileSync(new URL('src/praisonai-desktop/INSTALL.md', root), 'utf8');
const ui = readFileSync(new URL('src/praisonai-desktop/ui/index.html', root), 'utf8');

test('the release tag becomes the desktop product version before bundling', () => {
  const runnable = workflow
    .split('\n')
    .filter((line) => !/^\s*#/.test(line))
    .join('\n');
  const sync = runnable.indexOf('node src/praisonai-desktop/tools/set-release-version.mjs');
  const build = runnable.indexOf('cargo tauri build');
  assert.notEqual(sync, -1, 'the release never writes its tag into tauri.conf.json');
  assert.ok(sync < build, 'the desktop version is updated after the bundle is built');
  assert.equal(releaseVersion('v4.7.3'), '4.7.3');
  assert.equal(releaseVersion('4.8.0-rc.1'), '4.8.0-rc.1');
  assert.throws(() => releaseVersion('latest'), /not a semantic version/);
  assert.throws(() => releaseVersion('1.2.3-01'), /not a semantic version/);
});

test('the packaged About view reads the same Tauri version', () => {
  const start = ui.indexOf('{ key: "version", section: "about"');
  const end = ui.indexOf('{ key: "engine_status"', start);
  const desktopVersion = ui.slice(start, end);
  assert.match(ui,
               /__PRAISONAI_DESKTOP_VERSION__\s*=\s*await\s+window\.__TAURI__\.app\.getVersion\(\)/,
               'the UI does not assign the version embedded by Tauri to the About value');
  assert.match(desktopVersion, /__PRAISONAI_DESKTOP_VERSION__/,
               'About does not use the version returned by Tauri');
  assert.doesNotMatch(desktopVersion, /0\.1\.0/, 'About still hardcodes the development version');
  assert.ok(ui.includes('label: "PraisonAI Agents"'),
            'About does not distinguish the agents package from the desktop shell');
});

test('the Windows release fails if its embedded version drifts', () => {
  const start = workflow.indexOf('The Windows binary must carry the release version');
  const end = workflow.indexOf('The macOS bundle must carry a valid signature', start);
  const gate = workflow.slice(start, end);
  assert.match(gate, /VersionInfo/, 'the release never reads the binary version resource');
  assert.match(gate, /ProductVersion/, 'the release does not verify ProductVersion');
  assert.match(gate, /FileVersion/, 'the release does not verify FileVersion');
  assert.match(gate, /\$version\.ProductVersion\s+-ne\s+\$expected/,
               'ProductVersion is not compared with the release version');
  // FileVersion is compared by component, not as a string.
  //
  // This assertion used to require `$version.FileVersion -ne $numeric`, where
  // $numeric was the tag plus a literal ".0" -- so it pinned the very bug that
  // blocked the v4.7.4 Windows build: a binary correctly stamped 4.7.4 was
  // rejected for not reading "4.7.4.0". A test that requires the broken
  // comparison stops anyone fixing it, which is worse than no test.
  assert.match(gate, /\[version\]\$version\.FileVersion|\$got\s*=\s*\[version\]/,
               'FileVersion is not parsed as a version before comparison');
  assert.ok(!/\+\s*'\.0'/.test(gate),
            'the gate still appends ".0" and compares the string literally');
  assert.ok(start > workflow.indexOf('cargo tauri build'), 'the binary is checked before it exists');
  assert.ok(start < workflow.indexOf('gh release upload'), 'the binary is checked after upload');
});

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

test('no build runs on a retired or deprecating runner image', () => {
  // This has bitten twice. macos-13 was retired on 2026-12-04, so the Intel
  // leg would never have scheduled and the completeness check below would have
  // failed every release, forever, correctly. macos-14 then entered its own
  // deprecation, with brownouts that fail jobs before the final date -- and it
  // was the only Apple-silicon leg, so losing it means no arm64 DMG at all.
  //
  // A list of names, not a date check: the point is to fail here, next to the
  // reason, rather than at midnight on release day.
  const RETIRED = ['macos-11', 'macos-12', 'macos-13', 'macos-14',
                   'ubuntu-18.04', 'ubuntu-20.04', 'windows-2019'];
  for (const file of [workflow, ci]) {
    for (const image of RETIRED) {
      // Word boundary: macos-15-intel must not match macos-15, and macos-13
      // must not match macos-13-large.
      const used = new RegExp(`(?:runner|os):\\s*\\[?[^\\n]*\\b${image}\\b`);
      assert.ok(!used.test(file),
                `${image} is retired or deprecating; jobs on it fail or never schedule`);
    }
  }
});

test('every platform the app ships on is still built', () => {
  // Bumping a runner must not quietly drop a leg.
  assert.match(workflow, /runner:\s*macos-15\b/, 'no Apple-silicon build');
  assert.match(workflow, /runner:\s*macos-15-intel\b/, 'no Intel Mac build');
  assert.match(workflow, /runner:\s*windows-latest\b/, 'no Windows build');
  assert.match(workflow, /runner:\s*ubuntu-22\.04\b/, 'no Linux build');
});

test('the Linux build host is old enough for the glibc floor it promises', () => {
  // glibc is forward-compatible only: the build host decides the oldest
  // distribution the .deb can start on, and no runtime flag can widen it.
  assert.match(workflow, /runner:\s*ubuntu-22\.04/,
               'building Linux on a newer image silently drops older distributions');
  assert.ok(install.includes('22.04'), 'INSTALL.md does not say which distributions are supported');
});

test('the macOS window overlay repeats the base window faithfully', () => {
  // tauri.macos.conf.json has to restate the whole window object, because
  // Tauri merges with RFC 7386 and that replaces arrays wholesale rather than
  // merging their elements. An overlay carrying only the two macOS keys
  // deleted title, width, height and both minimums, and the app became an
  // 800x600 "Tauri App" that could be dragged down to nothing.
  //
  // Restating it means it can now drift instead. Nothing else would notice,
  // because the result is a window that is merely the wrong size.
  const overlay = JSON.parse(
    readFileSync(new URL('src/praisonai-desktop/src-tauri/tauri.macos.conf.json', root), 'utf8'));
  const base = config.app.windows[0];
  const mac = overlay.app.windows[0];
  for (const key of Object.keys(base)) {
    assert.deepEqual(mac[key], base[key],
                     `tauri.macos.conf.json disagrees about "${key}"`);
  }
  // And the two keys that are the whole reason the overlay exists.
  assert.equal(mac.titleBarStyle, 'Overlay');
  assert.equal(mac.hiddenTitle, true);
});

test('the macOS bundle is configured to be signed', () => {
  // Without an identity Tauri never runs codesign on the bundle, and the only
  // signature left is the one rustc's linker applies to the bare executable.
  // That signature's CodeDirectory declares a resource seal the unsigned
  // bundle does not have, so macOS calls the app "damaged and can't be
  // opened" -- not "unidentified developer" -- and right-click -> Open cannot
  // bypass it. v4.7.2 shipped exactly that.
  //
  // "-" is the ad-hoc identity. It is not a Developer ID and does not make the
  // app trusted; it makes the signature *valid*, which is the difference
  // between "damaged" and a warning the user can click past.
  const mac = config.bundle.macOS;
  assert.ok(mac, 'no macOS bundle config at all');
  // Pinned to "-", not merely truthy: any other value is either a Developer ID
  // we do not have (the build has no keychain to satisfy it, so codesign
  // fails) or a typo Tauri passes straight to codesign. Only "-" is the ad-hoc
  // identity that turns the shipped "damaged" bundle into a valid signature.
  assert.equal(mac.signingIdentity, '-',
               'the macOS bundle must use the ad-hoc signing identity "-"');
});

test('the release build verifies the signature before uploading', () => {
  // The config alone is not enough -- if Tauri ever stops honouring it, the
  // build must fail rather than attach another unopenable DMG.
  //
  // Comments are stripped first. The first version of this matched the phrase
  // "codesign --verify" inside the comment that explains the gate, so deleting
  // the actual command changed nothing and the test still passed.
  const runnable = workflow
    .split('\n')
    .filter((line) => !/^\s*#/.test(line))
    .join('\n');
  assert.match(runnable, /codesign\s+--verify\s+--deep\s+--strict/,
               'nothing checks the signature before the bundle is attached');
  assert.ok(runnable.indexOf('codesign --verify') < runnable.indexOf('gh release upload'),
            'the signature is verified after upload, which is too late');

  // The gate is worthless if it never runs. Its step is the only place the
  // codesign command lives, so pin that step to macOS: flipping the `if` to
  // skip macOS -- or dropping the condition so it runs on Linux where codesign
  // does not exist and the step is silently skipped -- would otherwise still
  // pass every assertion above.
  const stepStart = runnable.lastIndexOf('- name:',
                                         runnable.indexOf('codesign --verify'));
  const nextStep = runnable.indexOf('\n      - name:', stepStart + 1);
  const gate = runnable.slice(stepStart, nextStep === -1 ? undefined : nextStep);
  assert.match(gate, /if:\s*runner\.os\s*==\s*'macOS'/,
               'the signature-verification step is not scoped to macOS runners');
});

test('the signature gate reads the DMG, not the app beside it', () => {
  // Tauri deletes the app bundle once the DMG is built -- the build log says
  // so: "Cleaning .../bundle/macos/PraisonAI.app". A gate that looked for the
  // .app therefore found nothing and failed every macOS leg of v4.7.3, which
  // is why that release shipped with no Mac downloads at all.
  //
  // Reading the DMG is also the better check: it is the artifact people
  // download, and the one that was broken.
  const runnable = workflow
    .split('\n')
    .filter((line) => !/^\s*#/.test(line))
    .join('\n');
  const gate = runnable.slice(runnable.indexOf('must carry a valid signature'),
                              runnable.indexOf('Name the artifact'));
  assert.ok(gate, 'the signature gate is gone');
  assert.match(gate, /hdiutil attach/, 'the gate does not open the DMG');
  assert.match(gate, /-name '\*\.dmg'/, 'the gate does not look for a .dmg');
  assert.ok(!/-name '\*\.app' -print -quit"?\s*\)?\s*$/m.test(
              gate.split('hdiutil attach')[0]),
            'the gate looks for a .app before mounting; Tauri has deleted it by then');
  assert.match(gate, /hdiutil detach/, 'the gate never unmounts the DMG');
});

test('the macOS overlay does not drop the bundle configuration', () => {
  // Tauri merges the overlay with RFC 7386, which replaces rather than merges.
  // An overlay that grew a "bundle" key would silently discard the signing
  // identity along with everything else under it.
  const overlay = JSON.parse(
    readFileSync(new URL('src/praisonai-desktop/src-tauri/tauri.macos.conf.json', root), 'utf8'));
  if (overlay.bundle) {
    assert.ok(overlay.bundle.macOS?.signingIdentity,
              'the overlay defines bundle but omits signingIdentity, which replaces it away');
  }
});

test('the Windows version gate compares components, not the literal string', () => {
  // It appended ".0" and compared literally, so a binary correctly stamped
  // 4.7.4 was rejected against "4.7.4.0" and the v4.7.4 release shipped with
  // no Windows installer -- the one platform it was cut to fix. The stamping
  // was right; the check was not.
  const runnable = workflow
    .split('\n')
    .filter((line) => !/^\s*#/.test(line))
    .join('\n');
  const gate = runnable.slice(runnable.indexOf('must carry the release version'),
                              runnable.indexOf('must carry a valid signature'));
  assert.ok(gate, 'the Windows version gate is gone');
  assert.ok(!/\+ '\.0'/.test(gate),
            'the gate still appends ".0" and compares the string literally');
  assert.match(gate, /\$got\.Major|\[version\]/,
               'the gate does not compare version components');
  // The half that was always right must stay: a binary stamped 0.1.0 is the
  // bug this gate exists for.
  assert.match(gate, /ProductVersion/,
               'the gate no longer checks ProductVersion');
});
