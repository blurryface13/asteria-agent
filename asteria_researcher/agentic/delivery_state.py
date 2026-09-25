"""Publication progress is separate from research and durable user delivery."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def runtime_identity():
    return {key: os.getenv(env, 'unknown') for key, env in {
        'revision': 'ASTERIA_RUNTIME_REVISION', 'dirty': 'ASTERIA_RUNTIME_DIRTY',
        'started_at': 'ASTERIA_RUNTIME_STARTED_AT', 'service': 'ASTERIA_RUNTIME_SERVICE',
    }.items()}


def record_delivery(folder: Path, status: str, **detail):
    """Ready means files generated; only the durable DB can confirm delivery."""
    if status not in {'pending', 'publishing', 'ready', 'failed', 'cancelled'}:
        raise ValueError('Unknown publication state')
    payload = {'status': status, 'scope': 'artifact_generation',
               'authoritative_task_status': 'research_runs.status',
               'updated_at': datetime.now(timezone.utc).isoformat(),
               'runtime': runtime_identity(), **detail}
    path = folder / 'delivery-state.json'
    temporary = folder / 'delivery-state.tmp'
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    temporary.replace(path)
    return path
