"""Bounded live financial-report smoke; uses the configured paid model.

Run intentionally, not in CI. The test approves its own scope and leaves all
outputs under outputs/review_*. No key, prompt or report text is printed.
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


async def run(task, max_actions, online_rag):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'backend'))
    from asteria_researcher.agentic.autonomous import AutonomousReview
    from asteria_researcher.agentic.latex import publish
    from backend.finance.client import search as financial_search
    from backend.server.agentic_runner import configured_model
    from backend.auth.schema_bootstrap import initialize_database
    from asteria_researcher.config.config import Config
    from asteria_researcher.memory.embeddings import Memory

    await initialize_database()
    cfg = Config(os.getenv('CONFIG_PATH') or None)
    async def emit(kind, payload):
        if kind == 'agent_action' and payload.get('status') in {'completed', 'failed'}:
            print(payload['agent'], payload['tool'], payload['status'], flush=True)
    async def approve(_plan):
        return '确认'
    embedding = (Memory(cfg.embedding_provider, cfg.embedding_model,
                        **cfg.embedding_kwargs).get_embeddings() if online_rag else None)
    runtime = AutonomousReview(configured_model(os.getenv('CONFIG_PATH')), embedding,
        emit, approve, max_actions=max_actions, online_rag=online_rag,
        public_search=financial_search, capability='financial_research')
    try:
        report = await runtime.run(task)
        paths = await publish(report, Path('outputs'), profile=runtime.format_profile,
                              assets=runtime.figure_assets)
        print('COMPLETE', runtime.folder, paths, flush=True)
    except BaseException as error:
        print('INCOMPLETE', runtime.folder, type(error).__name__, flush=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', default=(
        '根据 NVIDIA 投资者关系官网公开的 FY2026 与 FY2025 年度报告，'
        '比较两年收入与经营现金流，说明报告期、币种和单位，并分析披露的一项主要风险。'
        '使用报告原文和邻近引文，写一份简洁的中文研究报告；不提供投资建议。'))
    parser.add_argument('--max-actions', type=int, default=48)
    parser.add_argument('--online-rag', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    load_dotenv(root / '.env')
    load_dotenv(root / '.env.lab', override=True)
    asyncio.run(run(args.task, args.max_actions, args.online_rag))
