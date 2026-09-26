"""Run this checkout's API/Worker against a separate local QA database.

Example (after creating the named database):
  python scripts/start-isolated-coding-qa.py api --env-file /path/to/existing/.env
  python scripts/start-isolated-coding-qa.py worker --env-file /path/to/existing/.env

Never modifies the source dotenv files. No existing API/Worker is stopped.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


def isolated_url(value: str, database: str) -> str:
    if not re.fullmatch(r"asteria_qa_[a-z0-9_]{1,40}", database):
        raise ValueError("QA database name must begin asteria_qa_ and use lowercase letters, digits or underscore")
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname or not parsed.path:
        raise ValueError("Existing DATABASE_URL is not a valid PostgreSQL URL")
    if parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Isolated coding QA may only use local PostgreSQL")
    if parsed.path.lstrip("/") == database:
        raise ValueError("Source DATABASE_URL already points to the QA database")
    return urlunsplit((parsed.scheme, parsed.netloc, "/" + database, parsed.query, parsed.fragment))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("api", "worker"))
    parser.add_argument("--env-file", action="append", required=True)
    parser.add_argument("--database", default="asteria_qa_coding_20260927")
    args = parser.parse_args()
    for path in args.env_file:
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        load_dotenv(path, override=True)
    old_url = os.environ.get("DATABASE_URL", "")
    os.environ["DATABASE_URL"] = isolated_url(old_url, args.database)
    os.environ["ASTERIA_API_HOST"] = "127.0.0.1"
    os.environ["ASTERIA_API_PORT"] = "8027"
    os.environ["ASTERIA_REDIS_URL"] = "redis://127.0.0.1:6379/9"
    os.environ["ASTERIA_REDIS_NAMESPACE"] = "asteria:qa:coding:20260927"
    os.environ["ASTERIA_WORKSPACES_ROOT"] = str(ROOT / "outputs" / "qa-workspaces")
    os.environ["ASTERIA_MEMORY_CHROMA_DIR"] = str(ROOT / "outputs" / "qa-workspaces" / ".memory-chroma")
    os.environ["ASTERIA_PUBLISH_PAPER_CORPUS"] = "0"
    os.environ["ASTERIA_EXPERIMENT_EXECUTOR"] = "local_docker"
    os.environ["ASTERIA_DEV_AUTH_BYPASS"] = "0"
    os.environ["ASTERIA_RESEARCH_CONCURRENCY"] = "1"
    os.environ["CORS_ALLOW_ORIGINS"] = "http://127.0.0.1:3024,http://localhost:3024"
    if args.service == "api":
        sys.argv = [str(ROOT / "scripts" / "start-research-service.py"), "api"]
    else:
        sys.argv = [str(ROOT / "scripts" / "start-research-service.py"), "worker"]
    print(f"Starting isolated {args.service} at code checkout {ROOT}, database={args.database}", flush=True)
    runpy.run_path(str(ROOT / "scripts" / "start-research-service.py"), run_name="__main__")


if __name__ == "__main__":
    main()
