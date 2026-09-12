// Run in frontend/nextjs. Load the actual SSR sanitizer graph before serving.
// Reject cloud-managed runtime locations instead of relying on rehydration.
const { createRequire } = require('node:module');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawnSync } = require('node:child_process');
const { realpathSync } = require('node:fs');
const os = require('node:os');

function assertLocalRuntime() {
  if (process.platform !== 'darwin') return;
  const cwd = realpathSync(process.cwd());
  const cloudRoots = ['Documents', 'Desktop', 'Library/Mobile Documents'].map(p => path.join(os.homedir(), p));
  if (cloudRoots.some(root => cwd === root || cwd.startsWith(root + path.sep))) {
    throw new Error('Run the project outside macOS cloud-managed folders (for example ~/Developer/asteria-agent). Cloud eviction can remove dependencies and build files while Next is running.');
  }
}

async function checkFrontendFiles() {
  assertLocalRuntime();
  const localRequire = createRequire(path.join(process.cwd(), 'package.json'));
  try {
    // Probe the Next server dependency chain as well as the sanitizer graph.
    // A missing SWC helper otherwise surfaces only after the first page
    // compilation, when the dev server can already be returning HTTP 500.
    localRequire.resolve('next/dist/client/next-dev.js');
    localRequire.resolve('@swc/helpers/_/_interop_require_wildcard');
    localRequire('jsdom');
    await import(pathToFileURL(localRequire.resolve('dompurify')).href);
  } catch (error) {
    throw new Error('Frontend runtime dependencies are not readable: ' + error.message +
      '. On macOS check ls -lO for dataless files; migrate the runtime outside cloud-managed folders and restore the exact lockfile versions. Do not disable sanitization or delete a running .next. ' +
      'The probe covers both Next/SWC and SSR sanitization dependencies.');
  }
  console.log('Next/SWC and SSR sanitizer dependency imports OK');
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
