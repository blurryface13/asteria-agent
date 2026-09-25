import asyncio

from scripts.report_token_usage import summarize


def test_usage_summary_separates_stages_and_unknown_cache():
    events = [
        {'payload': {'type': 'usage', 'stage': 'research_lead', 'usage': {
            'input_tokens': 100, 'output_tokens': 10, 'input_token_details': {'cache_read': 40}},
            'latency_ms': 200}},
        {'payload': {'type': 'usage', 'stage': 'citation_agent', 'usage': {
            'input_tokens': 20, 'cache_read_input_tokens': 30,
            'cache_creation_input_tokens': 10, 'output_tokens': 5}}},
        {'payload': {'type': 'usage', 'stage': 'writer', 'usage': {
            'input_tokens': 50, 'output_tokens': 5}}},
        {'payload': {'type': 'usage', 'stage': 'writer', 'usage': None, 'available': False}},
    ]
    report = summarize(events)
    assert report['total']['input_tokens'] == 210
    assert report['total']['cache_read_tokens'] == 70
    assert report['total']['cache_read_ratio'] is None
    assert report['by_stage']['research_lead']['cache_read_ratio'] == .4
    assert report['by_stage']['citation_agent']['input_tokens'] == 60
    assert report['by_stage']['writer']['missing_usage'] == 1


def test_model_call_emits_research_stage_without_sibling_leak(tmp_path):
    from asteria_researcher.agentic.autonomous import AutonomousReview
    from asteria_researcher.utils.usage_context import usage_sink, record_usage, track_usage_stage

    events = []

    async def model(_system, _payload):
        await record_usage('test', 'test', 1, {'input_tokens': 10, 'output_tokens': 2})
        return '{}'

    async def emit(*_args):
        pass

    async def approve(*_args):
        return None

    async def run():
        async def collect(event):
            events.append(event)
        token = usage_sink.set(collect)
        try:
            review = AutonomousReview(model, None, emit, approve, root=tmp_path, online_rag=False)

            async def invoke(stage):
                with track_usage_stage(stage):
                    return await review.llm('system', {'task': 'test'})

            await asyncio.gather(invoke('writer'), invoke('citation_agent'))
            await review.llm('system', {'task': 'test'})
        finally:
            usage_sink.reset(token)

    asyncio.run(run())
    assert {event['stage'] for event in events} == {'writer', 'citation_agent', 'research_lead'}
