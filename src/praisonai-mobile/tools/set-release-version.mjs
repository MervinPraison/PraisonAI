/**
 * Write the release version, and a monotonic build number, into the Tauri
 * config the mobile bundler reads.
 *
 * The desktop app shipped v4.7.3 whose installer reported ProductVersion
 * 0.1.0, because `tauri.conf.json` was hardcoded and the bundler read it
 * verbatim (#4527). `praisonai-mobile` has the identical hardcoded `0.1.0`,
 * and on a store the consequence is worse than a wrong label:
 *
 *   - Tauri derives Android `versionCode` from this file. Play REJECTS an
 *     upload whose versionCode has been used before.
 *   - It derives iOS `CFBundleVersion` from it. App Store Connect rejects a
 *     duplicate CFBundleVersion within a CFBundleShortVersionString.
 *
 * So with the version frozen, the FIRST upload succeeds and the second is
 * refused outright. A release process that works exactly once is not one.
 *
 * `tauri.conf.json` is the single source the bundler reads -- deliberately not
 * synced with package.json or Cargo.toml, the same single-source rule the
 * desktop package settled on.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const CONFIG = fileURLToPath(new URL("../src-tauri/tauri.conf.json", import.meta.url));
const NUMERIC = "(?:0|[1-9]\\d*)";
const PRERELEASE = `(?:${NUMERIC}|\\d*[A-Za-z-][0-9A-Za-z-]*)`;
const SEMVER = new RegExp(
  `^${NUMERIC}\\.${NUMERIC}\\.${NUMERIC}(?:-${PRERELEASE}(?:\\.${PRERELEASE})*)?` +
  "(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$");

/** Strip one conventional `v` prefix and validate a strict semantic version. */
export function releaseVersion(tag) {
  const version = tag?.startsWith("v") ? tag.slice(1) : tag;
  if (!version || !SEMVER.test(version)) {
    throw new Error(`release tag "${tag ?? ""}" is not a semantic version`);
  }
  return version;
}

/**
 * The store build number: strictly increasing, and independent of semver.
 *
 * Semver alone cannot serve. Both stores need a number that rises on EVERY
 * upload, including a re-upload of the same version after a rejection -- which
 * is precisely when a release is most likely to need one. CI passes
 * `github.run_number`, which only ever increases for a repository.
 */
export function buildNumber(run) {
  const n = Number(run);
  if (!Number.isInteger(n) || n < 1) {
    throw new Error(`build number "${run ?? ""}" is not a positive integer`);
  }
  return n;
}

/** Write both into the Tauri config consumed by the bundler. */
export function setReleaseVersion(tag, run, configPath = CONFIG) {
  const config = JSON.parse(readFileSync(configPath, "utf8"));
  config.version = releaseVersion(tag);
  if (run !== undefined) {
    config.bundle ??= {};
    config.bundle.android ??= {};
    config.bundle.iOS ??= {};
    config.bundle.android.versionCode = buildNumber(run);
    config.bundle.iOS.buildNumber = String(buildNumber(run));
  }
  writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`);
  return { version: config.version, build: run === undefined ? null : buildNumber(run) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const { version, build } = setReleaseVersion(process.argv[2], process.argv[3]);
    console.log(`mobile release version: ${version}${build === null ? "" : ` (build ${build})`}`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
