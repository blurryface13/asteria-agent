"""Server-only, administrator-managed model selection for agent roles."""
import base64
import hashlib
import os

from cryptography.fernet import Fernet

from backend.auth.db import get_pool

ROLES = ('intent_router', 'general_chat', 'research_lead', 'research_subagent',
         'coding_subagent', 'data_analyst', 'writer', 'citation_agent',
         'orchestrator_compose', 'financial_research', 'company_research')
MODELS = ('deepseek-chat', 'deepseek-reasoner')


def _cipher():
    secret = os.getenv('ASTERIA_MODEL_SETTINGS_SECRET') or os.getenv('JWT_SECRET')
    if not secret or len(secret) < 32:
        raise RuntimeError('模型密钥存储需要 ASTERIA_MODEL_SETTINGS_SECRET 或 32 字符以上 JWT_SECRET')
    derived = hashlib.sha256(b'asteria-agent-model-settings-v1:' + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


async def listing():
    rows = await (await get_pool()).fetch('SELECT role,model,key_tail,updated_at FROM agent_model_settings')
    by_role = {r['role']: r for r in rows}
    return [{'role': role, 'model': by_role[role]['model'] if role in by_role else None,
             'has_key': bool(by_role[role]['key_tail']) if role in by_role else False,
             'key_tail': by_role[role]['key_tail'] if role in by_role else None,
             'updated_at': by_role[role]['updated_at'] if role in by_role else None}
            for role in ROLES]


async def save(role, model, api_key=None, clear_key=False):
    if role not in ROLES or model not in MODELS:
        raise ValueError('不支持该角色或模型')
    if api_key is not None:
        api_key = api_key.strip()
        if not 8 <= len(api_key) <= 512 or any(c.isspace() for c in api_key):
            raise ValueError('API Key 格式无效')
    encrypted = _cipher().encrypt(api_key.encode()).decode() if api_key else None
    pool = await get_pool()
    await pool.execute('''INSERT INTO agent_model_settings(role,model,encrypted_key,key_tail)
        VALUES($1,$2,$3,$4) ON CONFLICT(role) DO UPDATE SET model=$2,
        encrypted_key=CASE WHEN $5 THEN NULL WHEN $3::text IS NOT NULL THEN $3 ELSE agent_model_settings.encrypted_key END,
        key_tail=CASE WHEN $5 THEN NULL WHEN $4::text IS NOT NULL THEN $4 ELSE agent_model_settings.key_tail END,
        updated_at=now()''', role, model, encrypted, api_key[-4:] if api_key else None, clear_key)


async def save_all(model, api_key):
    """Configure every role in a single statement for first-time setup.

    Explicitly overwrites individual role keys; later per-role edits still work.
    """
    if model not in MODELS:
        raise ValueError('不支持该模型')
    api_key = api_key.strip()
    if not 8 <= len(api_key) <= 512 or any(c.isspace() for c in api_key):
        raise ValueError('API Key 格式无效')
    encrypted = _cipher().encrypt(api_key.encode()).decode()
    await (await get_pool()).execute('''INSERT INTO agent_model_settings(role,model,encrypted_key,key_tail)
        SELECT role,$2,$3,$4 FROM unnest($1::text[]) AS role
        ON CONFLICT(role) DO UPDATE SET model=EXCLUDED.model,
        encrypted_key=EXCLUDED.encrypted_key, key_tail=EXCLUDED.key_tail,
        updated_at=now()''', list(ROLES), model, encrypted, api_key[-4:])


async def resolve(role, default_model):
    """A run's model closure caches this selection; updates affect later runs."""
    if role not in ROLES:
        return default_model, None
    row = await (await get_pool()).fetchrow(
        'SELECT model,encrypted_key FROM agent_model_settings WHERE role=$1', role)
    if not row:
        return default_model, None
    key = _cipher().decrypt(row['encrypted_key'].encode()).decode() if row['encrypted_key'] else None
    return row['model'], key


async def snapshot():
    """Freeze every role for one request/run; don't switch keys mid-report."""
    rows = await (await get_pool()).fetch('SELECT role,model,encrypted_key FROM agent_model_settings')
    result = {}
    for row in rows:
        if row['role'] not in ROLES or row['model'] not in MODELS:
            continue
        key = _cipher().decrypt(row['encrypted_key'].encode()).decode() if row['encrypted_key'] else None
        result[row['role']] = (row['model'], key)
    return result


async def revision():
    value = await (await get_pool()).fetchval('SELECT max(updated_at) FROM agent_model_settings')
    return value.isoformat() if value else ''
