"""Backup and provision a small lab. Secrets never appear in CLI arguments/logs."""
import argparse
import asyncio
from datetime import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def write_private(path,text):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f: f.write(text)


async def main(args):
    from dotenv import load_dotenv
    os.chdir(ROOT)
    load_dotenv(ROOT/'.env')
    load_dotenv(ROOT/'.env.lab',override=True)
    from backend.auth import lab
    from backend.auth.db import get_pool,close_pool
    from backend.auth.schema_bootstrap import initialize_database
    from backend.memory.service import root,key
    from pydantic import TypeAdapter,EmailStr
    email=str(TypeAdapter(EmailStr).validate_python(args.email)).casefold()
    pool=await get_pool()
    try:
        if args.action=='account':
            await initialize_database()
            password=getpass.getpass('Password (12+ characters): ')
            if password!=getpass.getpass('Repeat password: '): raise RuntimeError('Passwords differ')
            await lab.provision(email,password,args.name)
            print('Account provisioned; old sessions invalidated.')
            return
        active=await pool.fetchval("SELECT count(*) FROM research_runs WHERE status IN ('queued','running','waiting_approval','cancel_requested')")
        turns=await pool.fetchval("SELECT count(*) FROM coordinator_turns WHERE status='running'")
        indexes=await pool.fetchval("SELECT count(*) FROM knowledge_versions WHERE status IN ('queued','indexing')")
        if active or turns or indexes: raise RuntimeError('Active work exists; do not migrate/reload yet')
        tables={'workspace_projects':'user_email','workspace_conversations':'user_email','research_runs':'user_email','reports':'user_email','knowledge_bases':'owner'}
        counts={t:await pool.fetchval(f'SELECT count(*) FROM {t} WHERE {column}=$1',args.source) for t,column in tables.items()}
        print(json.dumps({'source':args.source,'target':email,'owned_records':counts},ensure_ascii=False))
        if not args.apply:
            print('Dry run only. Use --apply after checking the source identity.')
            return
        backup=Path(args.backup_dir).expanduser().absolute()/datetime.now().strftime('%Y%m%d-%H%M%S')
        backup.mkdir(parents=True,mode=0o700)
        from urllib.parse import urlparse,unquote
        connection=urlparse(os.environ['DATABASE_URL'])
        env=dict(os.environ,PGDATABASE=unquote(connection.path.lstrip('/')),
                 PGHOST=connection.hostname or 'localhost',PGPORT=str(connection.port or 5432),
                 PGUSER=unquote(connection.username or getpass.getuser()))
        if connection.password: env['PGPASSWORD']=unquote(connection.password)
        dump=backup/'database.dump'
        with dump.open('xb') as out:
            os.chmod(dump,0o600)
            result=subprocess.run(['pg_dump','--format=custom','--no-owner'],env=env,stdout=out,stderr=subprocess.PIPE)
        if result.returncode: raise RuntimeError('pg_dump failed; database not changed')
        check=subprocess.run(['pg_restore','--list',str(dump)],capture_output=True)
        if check.returncode: raise RuntimeError('Backup archive validation failed; database not changed')
        old=root()/'users'/key(args.source)
        new=root()/'users'/key(email)
        files=[]
        if old.exists():
            for p in old.rglob('*'):
                if p.is_symlink(): raise RuntimeError('Memory contains symlinks; manual review required')
                if p.is_file():
                    dest=new/p.relative_to(old)
                    if dest.exists() and dest.read_bytes()!=p.read_bytes(): raise RuntimeError('Target memory collision; refusing overwrite')
                    files.append((p,dest))
            shutil.copytree(old,backup/'source-workspace')
        # Existing output contents are not changed. Grant only when every current
        # report/run owner is the confirmed local or target identity.
        owners=set(await pool.fetch('SELECT DISTINCT user_email FROM research_runs UNION SELECT DISTINCT user_email FROM reports'))
        if any(r['user_email'] not in {args.source,email} for r in owners):
            raise RuntimeError('Mixed output owners; review legacy artifact mappings manually')
        artifacts=['outputs/'+str(p.relative_to(ROOT/'outputs')) for p in (ROOT/'outputs').rglob('*')
                   if p.is_file() and not any(q.is_symlink() for q in (p,*p.parents))]
        write_private(backup/'migration.json',json.dumps({'source':args.source,'target':email,'counts':counts,'legacy_artifacts':artifacts},ensure_ascii=False,indent=2))
        await initialize_database()
        for source,dest in files:
            dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            if not dest.exists(): shutil.copy2(source,dest)
        async with pool.acquire() as c,c.transaction():
            for table,column in tables.items():
                await c.execute(f'UPDATE {table} SET {column}=$1 WHERE {column}=$2',email,args.source)
            await c.execute('''UPDATE workspace_projects SET workspace_path=replace(workspace_path,$1,$2)
                WHERE user_email=$3 AND left(workspace_path,length($1)+1)=$1 || '/' ''',str(old),str(new),email)
            await c.executemany('INSERT INTO legacy_artifact_owners(path,user_email) VALUES($1,$2) ON CONFLICT(path) DO NOTHING',[(p,email) for p in artifacts])
        # Provision only once; re-running a migration must not reset a password.
        if not await pool.fetchval('SELECT password_hash FROM users WHERE email=$1',email):
            password=secrets.token_urlsafe(18)
            await lab.provision(email,password,args.name or '实验室管理员')
            write_private(backup/'administrator-login.txt',f'Email: {email}\nPassword: {password}\nChange via /accounts after first login.\n')
        print(json.dumps({'backup':str(backup),'migrated':counts,'legacy_artifacts':len(artifacts),'source_files_preserved':True},ensure_ascii=False))
    finally:
        await close_pool()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['account','migrate'])
    parser.add_argument('--email',required=True)
    parser.add_argument('--name',default='')
    parser.add_argument('--source',default='local@asteria.dev')
    parser.add_argument('--backup-dir',default=str(ROOT.parent/'asteria-private'/'backups'))
    parser.add_argument('--apply',action='store_true')
    asyncio.run(main(parser.parse_args()))
