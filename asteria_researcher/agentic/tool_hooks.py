"""Pre/post/failure hook projection of the runtime's authoritative event stream.

Same call-ID/parent-call association as Anthropic's SDK demo, without its
mutable global current-parent (unsafe for concurrently running Python tasks).
"""
from contextvars import ContextVar
import hashlib
import json
import time


class ToolHooks:
    def __init__(self, run_id):
        self.run_id = run_id
        self.parent = ContextVar('research_parent_' + run_id, default=None)
        self.pending = {}

    def record(self, event):
        identifier = event.get('call_id')
        if not identifier:
            return None
        status = event['status']
        if status == 'started':
            self.pending[identifier] = {'parent_call_id': event.get('parent_call_id', self.parent.get()),
                                        'started': time.monotonic()}
        state = self.pending.get(identifier, {})
        result = {'trace_id': self.run_id, 'call_id': identifier, 'agent': event['agent'],
                  'tool': event['tool'], 'status': status, 'time': event['time'],
                  'parent_call_id': state.get('parent_call_id'),
                  'hook': 'PreToolUse' if status == 'started' else 'PostToolUse' if status == 'completed' else 'ToolFailure'}
        if status != 'started':
            result['seconds'] = round(time.monotonic() - state.get('started', time.monotonic()), 3)
            self.pending.pop(identifier, None)
        # Do not duplicate raw documents or credentials into a second log.
        for key in ('arguments', 'result'):
            if key in event:
                value = json.dumps(event[key], ensure_ascii=False, default=str).encode()
                result[key + '_bytes'] = len(value)
                result[key + '_sha256'] = hashlib.sha256(value).hexdigest()
        return result
