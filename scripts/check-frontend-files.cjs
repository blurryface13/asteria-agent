// Run in frontend/nextjs. Load the actual SSR sanitizer graph before serving.
// An interactive run also lets macOS materialize its cloud-only dependencies.
const { createRequire } = require('node:module');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawnSync } = require('node:child_process');

async function checkFrontendFiles() {
  const localRequire = createRequire(path.join(process.cwd(), 'package.json'));
  try {
    localRequire('jsdom');
    await import(pathToFileURL(localRequire.resolve('dompurify')).href);
  } catch (error) {
    throw new Error('SSR sanitization dependencies are not readable: ' + error.message +
      '. On macOS check ls -lO for dataless files; run this check in an interactive terminal ' +
      'to restore downloaded content, then restart the frontend. Do not disable sanitization or delete .next.');
  }
  console.log('SSR sanitizer dependency imports OK');
}

module.exports = checkFrontendFiles;
if (require.main === module) {
  if (process.argv.includes('--probe')) {
    checkFrontendFiles().catch(error => { console.error(error.message); process.exitCode = 1; });
  } else {
    const probe = spawnSync(process.execPath, [__filename, '--probe'], { stdio: 'inherit', timeout: 30000 });
    if (probe.error) console.error('SSR dependency check timed out or failed:', probe.error.message);
    process.exitCode = probe.status === 0 ? 0 : 1;
  }
}
