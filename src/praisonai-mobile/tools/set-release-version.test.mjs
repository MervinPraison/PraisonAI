/**
 * The release version writer.
 *
 * Desktop shipped an installer reporting ProductVersion 0.1.0 because its
 * Tauri config was hardcoded (#4527). Mobile had the identical hardcoded
 * 0.1.0 and, on a store, the second upload is rejected outright rather than
 * merely mislabelled -- Play refuses a repeated versionCode and App Store
 * Connect a repeated CFBundleVersion.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { releaseVersion, buildNumber, setReleaseVersion } from "./set-release-version.mjs";

const fixture = (version = "0.1.0") => {
  const path = join(mkdtempSync(join(tmpdir(), "conf-")), "tauri.conf.json");
  writeFileSync(path, JSON.stringify({
    version,
    identifier: "ai.praison.mobile",
    bundle: { iOS: { minimumSystemVersion: "16.0" }, android: { minSdkVersion: 26 } },
  }, null, 2));
  return path;
};

test("a release tag becomes the version the bundler reads", () => {
  const path = fixture();
  const { version } = setReleaseVersion("v4.8.0", "17", path);
  assert.equal(version, "4.8.0");
  assert.equal(JSON.parse(readFileSync(path, "utf8")).version, "4.8.0", "written, not just returned");
});

test("one conventional v is stripped, and only one", () => {
  assert.equal(releaseVersion("v1.2.3"), "1.2.3");
  assert.equal(releaseVersion("1.2.3"), "1.2.3");
  assert.throws(() => releaseVersion("vv1.2.3"), /not a semantic version/);
});

test("a tag that is not semver is refused, not guessed at", () => {
  // A bad tag must stop the release. Writing something plausible would ship a
  // version nobody chose, which is how #4527 shipped in the first place.
  for (const tag of ["", undefined, "latest", "1.2", "v1.2.3.4", "release-1"]) {
    assert.throws(() => releaseVersion(tag), /not a semantic version/, String(tag));
  }
});

test("the build number rises on every upload, independent of semver", () => {
  // The case semver cannot serve: a re-upload of the SAME version after a
  // store rejection still needs a higher number, and that is exactly when a
  // release most needs one.
  const path = fixture();
  const first = setReleaseVersion("v4.8.0", "17", path);
  const second = setReleaseVersion("v4.8.0", "18", path);

  assert.equal(first.version, second.version, "the same release");
  assert.ok(second.build > first.build, "with a higher build number");

  const conf = JSON.parse(readFileSync(path, "utf8"));
  assert.equal(conf.bundle.android.versionCode, 18, "Play reads versionCode as an integer");
  assert.equal(conf.bundle.iOS.buildNumber, "18", "and CFBundleVersion is a string");
});

test("a build number that cannot increase is refused", () => {
  for (const run of ["0", "-1", "1.5", "abc", ""]) {
    assert.throws(() => buildNumber(run), /positive integer/, String(run));
  }
});

test("the platform minimums survive the rewrite -- the pair", () => {
  // The writer rewrites the whole file. Dropping a key it does not manage
  // would silently lower the deployment target.
  const path = fixture();
  setReleaseVersion("v4.8.0", "17", path);
  const conf = JSON.parse(readFileSync(path, "utf8"));
  assert.equal(conf.bundle.iOS.minimumSystemVersion, "16.0");
  assert.equal(conf.bundle.android.minSdkVersion, 26);
  assert.equal(conf.identifier, "ai.praison.mobile");
});
