from typing import Any

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    workspace_path: str | None = Field(default=None, max_length=1000)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    workspace_path: str | None = Field(default=None, max_length=1000)
    settings: dict[str, Any] | None = None


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="新任务", min_length=1, max_length=255)
    mode: str = Field(default="research", min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class MessageCreateRequest(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
