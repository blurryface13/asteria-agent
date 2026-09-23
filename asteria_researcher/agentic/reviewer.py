"""Independent acceptance role; invoked on delivery, not every N tool calls."""
from .base_agent import AgentProfile


class ReviewerAgent:
    profile = AgentProfile(
        'reviewer', '独立验收用户目标、证据与代码交付，返回具体缺口而不派发任务。',
        '确认目标、实际证据与交付产物', '是否可交付、逐目标发现与未完成项', (), 1)

    def __init__(self, assess_evidence, assess_implementation, emit):
        self.assess_evidence = assess_evidence
        self.assess_implementation = assess_implementation
        self.emit = emit

    async def run(self):
        await self.emit('reviewer', 'acceptance', 'started', 'Lead 准备交付，独立验收目标与实际证据')
        assessment = await self.assess_evidence()
        implementation = await self.assess_implementation()
        ready = assessment['ready'] and all(f['supported'] for f in implementation)
        await self.emit('reviewer', 'acceptance', 'completed' if ready else 'needs_followup',
                        '验收通过' if ready else '返回缺口，由 Lead 决定后续动作',
                        result={'ready':ready, 'assessment':assessment, 'implementation':implementation})
        return assessment, implementation
