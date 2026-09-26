"""Stable entry point for the API or independent worker, including launchd.

Run with the project's dora Python. Authentication and credentials stay in the
environment or repository .env; this entry point does not disable authentication.
"""
import argparse
import os
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('service', choices=('api', 'worker'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if sys.platform == 'darwin':
        cloud_roots = [Path.home() / folder for folder in ('Documents', 'Desktop', 'Library/Mobile Documents')]
        if any(root.is_relative_to(folder) for folder in cloud_roots):
            raise RuntimeError('Run from a local directory such as ~/Developer/asteria-agent, not a macOS cloud-managed folder. Configuration, source and artifacts must remain locally readable.')
    os.chdir(root)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'backend'))
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    load_dotenv(root / '.env.lab',override=True)
    # GUI process managers do not inherit a terminal's conda/Homebrew PATH.
    paths = [str(Path(sys.executable).parent)]
    paths += [p for p in ('/opt/homebrew/bin', '/Library/TeX/texbin') if Path(p).is_dir()]
    paths += os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin').split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join(dict.fromkeys(paths))
    # Freeze this process's code identity before importing application modules.
    # Environment configured revisions cannot pretend to describe this checkout.
    import subprocess
    from datetime import datetime, timezone
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = str(bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip())).lower()
    except (OSError, subprocess.CalledProcessError):
        # Packaged/Docker deployments may intentionally omit Git metadata.
        revision, dirty = os.getenv('ASTERIA_BUILD_REVISION', 'unknown'), 'unknown'
    os.environ['ASTERIA_RUNTIME_REVISION'], os.environ['ASTERIA_RUNTIME_DIRTY'] = revision, dirty
    os.environ['ASTERIA_RUNTIME_STARTED_AT'] = datetime.now(timezone.utc).isoformat()
    os.environ['ASTERIA_RUNTIME_SERVICE'] = args.service
    if args.service == 'worker':
        runpy.run_module('backend.runs.worker', run_name='__main__')
    else:
        import uvicorn
        # Some resolver combinations install Uvicorn without re-exporting
        # ``run`` from the package root. Keep the deployment entrypoint
        # compatible with both layouts.
        server_run = getattr(uvicorn, 'run', None)
        if server_run is None:
            from uvicorn.main import run as server_run
        server_run(
            'main:app',
            host=os.getenv('ASTERIA_API_HOST', '127.0.0.1'),
            port=int(os.getenv('ASTERIA_API_PORT', '8018')),
            # uvloop is not required and may be unavailable on WSL/Docker
            # builds; the built-in asyncio loop is portable.
            loop='asyncio',
        )


if __name__ == '__main__':
    main()
