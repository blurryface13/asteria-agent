"""PostgreSQL is the source of truth. All mutations serialize on the run row.

Only queued jobs are claimable. Expired executing jobs are interrupted, never
automatically retried: the external side effect of an in-flight tool is unknown.
"""
import hashlib
import json
from uuid import uuid4

from fastapi import HTTPException
from backend.auth.db import get_pool

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


async def event(conn, run_id, payload):
    seq = await conn.fetchval('UPDATE research_runs SET sequence=sequence+1 WHERE id=$1 RETURNING sequence', run_id)
    await conn.execute('INSERT INTO research_events(run_id,sequence,payload) VALUES($1,$2,$3)', run_id, seq, payload)
    return seq


async def owned(conn, run_id, email, lock=False):
    row = await conn.fetchrow('SELECT * FROM research_runs WHERE id=$1 AND user_email=$2' + (' FOR UPDATE' if lock else ''), run_id, email)
    if row is None:
        raise HTTPException(404, 'run not found')
    return row


async def fenced(conn, run_id, worker_id):
    row = await conn.fetchrow('SELECT * FROM research_runs WHERE id=$1 FOR UPDATE', run_id)
    valid = await conn.fetchval('SELECT lease_until > now() AND worker_id=$2 FROM research_jobs WHERE run_id=$1', run_id, worker_id)
    if not row or row['status'] in TERMINAL or not valid:
        raise RuntimeError('Research worker lease lost; refusing stale writes')
    return row


class RunStore:
    async def submit(self, email, key, conversation_id, request):
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            # Serialize same key and same conversation even across API processes.
            await c.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))', email + ':' + key)
            prior = await c.fetchrow('SELECT * FROM research_runs WHERE user_email=$1 AND request_key=$2', email, key)
            if prior:
                if prior['request_hash'] != digest or prior['conversation_id'] != conversation_id:
                    raise HTTPException(409, 'request_id already used for a different request')
                return dict(prior)
            conversation = await c.fetchrow('SELECT id FROM workspace_conversations WHERE id=$1 AND user_email=$2 FOR UPDATE', conversation_id, email)
            if not conversation:
                raise HTTPException(404, 'conversation not found')
            active = await c.fetchval("SELECT id FROM research_runs WHERE conversation_id=$1 AND status IN ('queued','running','waiting_approval','cancel_requested')", conversation_id)
            if active:
                raise HTTPException(409, 'This conversation already has an active run')
            run_id = uuid4().hex
            await c.execute('INSERT INTO research_runs(id,user_email,conversation_id,request_key,request_hash,request) VALUES($1,$2,$3,$4,$5,$6)', run_id, email, conversation_id, key, digest, request)
            await c.execute('INSERT INTO research_jobs(id,run_id) VALUES($1,$2)', uuid4().hex, run_id)
            await event(c, run_id, {'type': 'run_state', 'status': 'queued'})
            return dict(await owned(c, run_id, email))

    async def get(self, email, run_id):
        pool = await get_pool()
        async with pool.acquire() as c:
            row = dict(await owned(c, run_id, email))
            row['artifacts'] = [dict(r) for r in await c.fetch('SELECT kind,path,sha256,size_bytes FROM research_artifacts WHERE run_id=$1', run_id)]
            row['approval'] = await c.fetchrow("SELECT id,question FROM research_approvals WHERE run_id=$1 AND state='pending'", run_id)
            row['approval'] = dict(row['approval']) if row['approval'] else None
            usage = await c.fetch("SELECT payload FROM research_events WHERE run_id=$1 AND payload->>'type'='usage'", run_id)
            available = [r['payload']['usage'] for r in usage if r['payload'].get('usage')]
            def total(key):
                values = [u.get(key) for u in available]
                return sum(v for v in values if isinstance(v, int)) if any(isinstance(v, int) for v in values) else None
            row['usage'] = {'calls_recorded': len(usage), 'calls_with_usage': len(available),
                            'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
                            'total_tokens': total('total_tokens'), 'cost': None}
            row['timing'] = dict(await c.fetchrow('''SELECT
              extract(epoch from (coalesce(started_at,finished_at,now())-created_at)) AS queued_seconds,
              CASE WHEN started_at IS NULL THEN NULL ELSE extract(epoch from (coalesce(finished_at,now())-started_at)) END AS execution_seconds,
              (SELECT coalesce(sum(extract(epoch from (coalesce(a.answered_at,r.finished_at,now())-a.created_at))),0)
               FROM research_approvals a WHERE a.run_id=r.id) AS approval_seconds
              FROM research_runs r WHERE id=$1''', run_id))
            return row

    async def latest(self, email, conversation_id):
        pool = await get_pool()
        async with pool.acquire() as c:
            row = await c.fetchrow('SELECT id FROM research_runs WHERE user_email=$1 AND conversation_id=$2 ORDER BY created_at DESC LIMIT 1', email, conversation_id)
        return await self.get(email, row['id']) if row else None

    async def events(self, email, run_id, after=0, limit=200):
        pool = await get_pool()
        async with pool.acquire() as c:
            await owned(c, run_id, email)
            return [dict(r) for r in await c.fetch('SELECT sequence,payload,created_at FROM research_events WHERE run_id=$1 AND sequence>$2 ORDER BY sequence LIMIT $3', run_id, after, limit)]

    async def append(self, run_id, worker_id, payload):
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            await fenced(c, run_id, worker_id)
            return await event(c, run_id, payload)

    async def claim(self, worker_id):
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            row = await c.fetchrow("SELECT * FROM research_runs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
            if not row:
                return None
            await c.execute("UPDATE research_runs SET status='running',started_at=now() WHERE id=$1", row['id'])
            await c.execute("UPDATE research_jobs SET worker_id=$2,heartbeat_at=now(),lease_until=now()+interval '45 seconds' WHERE run_id=$1", row['id'], worker_id)
            await event(c, row['id'], {'type': 'run_state', 'status': 'running'})
            return dict(row)

    async def heartbeat(self, run_id, worker_id):
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            row = await fenced(c, run_id, worker_id)
            await c.execute("UPDATE research_jobs SET heartbeat_at=now(),lease_until=now()+interval '45 seconds' WHERE run_id=$1", run_id)
            return row['status']

    async def reap(self):
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            rows = await c.fetch("SELECT r.id FROM research_runs r JOIN research_jobs j ON j.run_id=r.id WHERE r.status IN ('running','waiting_approval','cancel_requested') AND j.lease_until<now() FOR UPDATE OF r SKIP LOCKED")
            for row in rows:
                reason = '后台执行进程失联；已保留事件和产物，未自动重跑。'
                await c.execute("UPDATE research_runs SET status='interrupted',error=$2,finished_at=now() WHERE id=$1", row['id'], reason)
                await c.execute("UPDATE research_approvals SET state='closed' WHERE run_id=$1 AND state='pending'", row['id'])
                await event(c, row['id'], {'type': 'run_state', 'status': 'interrupted', 'error': reason})
            return len(rows)

    async def cancel(self, email, run_id):
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            row = await owned(c, run_id, email, True)
            if row['status'] in TERMINAL or row['status'] == 'cancel_requested':
                return
            state = 'cancelled' if row['status'] == 'queued' else 'cancel_requested'
            await c.execute('UPDATE research_runs SET status=$2,finished_at=CASE WHEN $2=\'cancelled\' THEN now() ELSE NULL END WHERE id=$1', run_id, state)
            await event(c, run_id, {'type': 'run_state', 'status': state})

    async def ask(self, run_id, worker_id, question):
        approval_id = uuid4().hex
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            row = await fenced(c, run_id, worker_id)
            if row['status'] == 'cancel_requested':
                raise RuntimeError('Cancellation requested')
            await c.execute('INSERT INTO research_approvals(id,run_id,question) VALUES($1,$2,$3)', approval_id, run_id, question)
            await c.execute("UPDATE research_runs SET status='waiting_approval' WHERE id=$1", run_id)
            await event(c, run_id, {'type': 'human_feedback', 'content': 'request', 'output': question, 'approval_id': approval_id})
        return approval_id

    async def answer(self, email, run_id, approval_id, response):
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            row = await owned(c, run_id, email, True)
            approval = await c.fetchrow('SELECT * FROM research_approvals WHERE id=$1 AND run_id=$2', approval_id, run_id)
            if not approval:
                raise HTTPException(404, 'approval not found')
            if approval['state'] == 'answered' and approval['response'] == response:
                return
            if row['status'] != 'waiting_approval' or approval['state'] != 'pending':
                raise HTTPException(409, 'approval is no longer pending')
            await c.execute("UPDATE research_approvals SET state='answered',response=$2,answered_at=now() WHERE id=$1", approval_id, response)
            await c.execute("UPDATE research_runs SET status='running' WHERE id=$1", run_id)
            await event(c, run_id, {'type': 'approval_resolved', 'approval_id': approval_id})

    async def response(self, run_id, worker_id, approval_id):
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            await fenced(c, run_id, worker_id)
            row = await c.fetchrow('SELECT state,response FROM research_approvals WHERE id=$1 AND run_id=$2', approval_id, run_id)
            return (row['state'] == 'answered', row['response'])

    async def finish(self, run_id, worker_id, state, error=None, artifacts=None):
        if state not in TERMINAL:
            raise ValueError('invalid terminal state')
        pool = await get_pool()
        async with pool.acquire() as c, c.transaction():
            row = await fenced(c, run_id, worker_id)
            if row['status'] == 'cancel_requested':
                state = 'cancelled'
            for artifact in artifacts or []:
                await c.execute('INSERT INTO research_artifacts(run_id,kind,path,sha256,size_bytes) VALUES($1,$2,$3,$4,$5) ON CONFLICT(run_id,kind) DO NOTHING', run_id, artifact['kind'], artifact['path'], artifact['sha256'], artifact['size_bytes'])
            # Save the delivered report on the server, even if no browser is open.
            if state == 'completed':
                records = await c.fetch('SELECT payload FROM research_events WHERE run_id=$1 ORDER BY sequence', run_id)
                ordered = [{'type': 'question', 'content': row['request']['task']}]
                answer = ''
                for r in records:
                    p = r['payload']
                    if p.get('type') in {'usage', 'run_state', 'approval_resolved'}:
                        continue
                    ordered.append(p)
                    if p.get('type') == 'report':
                        answer += str(p.get('output', ''))
                    elif p.get('type') == 'report_complete':
                        answer = str(p.get('output', ''))
                    elif p.get('content') == 'research_report':
                        output = p.get('output')
                        answer = output if isinstance(output, str) else (output or {}).get('report', answer)
                if not answer.strip():
                    raise RuntimeError('Cannot complete a run without a report')
                await c.execute('''INSERT INTO reports(id,user_email,question,answer,ordered_data,chat_messages,"timestamp") VALUES($1,$2,$3,$4,$5,$6,extract(epoch from now())*1000)
                  ON CONFLICT(id) DO UPDATE SET answer=EXCLUDED.answer,ordered_data=EXCLUDED.ordered_data,"timestamp"=EXCLUDED."timestamp" WHERE reports.user_email=EXCLUDED.user_email''', row['conversation_id'], row['user_email'], row['request']['task'], answer, ordered, [])
            await c.execute('UPDATE research_runs SET status=$2,error=$3,finished_at=now() WHERE id=$1', run_id, state, error)
            await c.execute("UPDATE research_approvals SET state='closed' WHERE run_id=$1 AND state='pending'", run_id)
            await event(c, run_id, {'type': 'run_state', 'status': state, 'error': error})
