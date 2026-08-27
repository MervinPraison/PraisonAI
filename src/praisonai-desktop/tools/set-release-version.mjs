import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';

const CONFIG = fileURLToPath(new URL('../src-tauri/tauri.conf.json', import.meta.url));
const NUMERIC = '(?:0|[1-9]\\d*)';
const PRERELEASE = `(?:${NUMERIC}|\\d*[A-Za-z-][0-9A-Za-z-]*)`;
const SEMVER = new RegExp(
  `^${NUMERIC}\\.${NUMERIC}\\.${NUMERIC}(?:-${PRERELEASE}(?:\\.${PRERELEASE})*)?` +
  '(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?$');

/** Strip one conventional `v` prefix and validate a strict semantic version. */
export function releaseVersion(tag) {
  const version = tag?.startsWith('v') ? tag.slice(1) : tag;
  if (!version || !SEMVER.test(version)) {
    throw new Error(`release tag "${tag ?? ''}" is not a semantic version`);
  }
  return version;
}

/** Write the release version into the Tauri config consumed by the bundler. */
export function setReleaseVersion(tag, configPath = CONFIG) {
  const config = JSON.parse(readFileSync(configPath, 'utf8'));
  config.version = releaseVersion(tag);
  writeFileSync(configPath, `${JSON.stringify(config, null, 2)}\n`);
  return config.version;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const version = setReleaseVersion(process.argv[2]);
    console.log(`desktop release version: ${version}`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
