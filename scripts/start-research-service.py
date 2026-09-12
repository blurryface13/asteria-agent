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
    os.chdir(root)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'backend'))
    from dotenv import load_dotenv
    load_dotenv(root / '.env')
    # GUI process managers do not inherit a terminal's conda/Homebrew PATH.
    paths = [str(Path(sys.executable).parent)]
    paths += [p for p in ('/opt/homebrew/bin', '/Library/TeX/texbin') if Path(p).is_dir()]
    paths += os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin').split(os.pathsep)
    os.environ['PATH'] = os.pathsep.join(dict.fromkeys(paths))
    if args.service == 'worker':
        runpy.run_module('backend.runs.worker', run_name='__main__')
    else:
        import uvicorn
        uvicorn.run('main:app', host='127.0.0.1', port=int(os.getenv('ASTERIA_API_PORT', '8018')))


if __name__ == '__main__':
    main()
