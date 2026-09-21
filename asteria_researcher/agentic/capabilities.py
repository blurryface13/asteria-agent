"""Role contracts extend the Coordinator, not the existing research workflow."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Profile:
    id: str
    title: str
    description: str
    skill_id: str
    tools: tuple[str, ...]


PROFILES = {
    p.id: p for p in (
        Profile('workspace_coding','代码与实验准备助手','调查公开GitHub仓库、查看个人工作区代码、提出文件变更；遇到科学方法疑问可定向请求调研；不执行代码，修改必须用户确认',
                'workspace_assistance',('list_workspace_files','read_workspace_file','propose_workspace_change',
                                        'inspect_repository','read_repository_file','search_papers','read_paper',
                                        'read_paper_passage','check_python_syntax','preview_code_diff','request_research')),
        Profile('learning_guidance','学习指导','解释学习问题、制定学习路径与练习；不触发完整研究报告',
                'learning_assistance',('search_lab_knowledge',)),
        Profile('submission_consulting','投稿咨询','核查会议/期刊投稿范围、日期、材料与规范，需来源与年份',
                'submission_assistance',('search_public_sources','search_lab_knowledge')),
        Profile('financial_research','金融资料研究','金融知识解释、公开财务和行业资料分析；不交易、不保证收益',
                'finance_assistance',('search_public_sources',)),
        Profile('company_research','企业公开信息背调','核查公司主体、业务和公开风险，区分事实与待核实信息；不查询个人隐私',
                'company_assistance',('search_public_sources',)),
    )
}
RESEARCH = {'literature_review','experiment_design','general_research'}
CAPABILITIES = RESEARCH | {'general_chat','knowledge_chat'} | set(PROFILES)


def profile_catalog():
    return [asdict(p) for p in PROFILES.values()]
