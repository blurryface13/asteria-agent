from backend.auth.workspace_models import (
    ConversationCreateRequest,
    MessageCreateRequest,
    ProjectCreateRequest,
)
from backend.server.app import app


def _effective_paths():
    paths = []
    for route in app.router.routes:
        if hasattr(route, "effective_route_contexts"):
            paths.extend(context.path for context in route.effective_route_contexts())
        elif getattr(route, "path", None):
            paths.append(route.path)
    return paths


def test_workspace_request_contracts_normalize_expected_defaults():
    project = ProjectCreateRequest(name="  文献综述  ")
    conversation = ConversationCreateRequest()
    message = MessageCreateRequest(role="assistant", content="完成")

    assert project.name == "  文献综述  "
    assert project.settings == {}
    assert conversation.title == "新任务"
    assert conversation.mode == "research"
    assert message.metadata == {}


def test_workspace_routes_are_registered():
    paths = _effective_paths()

    assert "/api/workspace/projects" in paths
    assert "/api/workspace/projects/{project_id}" in paths
    assert "/api/workspace/conversations" in paths
    assert "/api/workspace/conversations/{conversation_id}/messages" in paths
