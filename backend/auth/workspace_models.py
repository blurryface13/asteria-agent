from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    workspace_path: str | None = Field(default=None, max_length=1000)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    workspace_path: str | None = Field(default=None, max_length=1000)
    settings: dict[str, Any] | None = None

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError('项目名称不能为空')
        return value.strip() if value is not None else value


class ConversationCreateRequest(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=100)
    title: str = Field(default="新任务", min_length=1, max_length=255)
    mode: str = Field(default="research", min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)

    @field_validator('title')
    @classmethod
    def nonblank_title(cls, value):
        if not value.strip():
            raise ValueError('任务名称不能为空')
        return value.strip()


class ConversationMoveRequest(BaseModel):
    # Required null means detach; omission must not accidentally ungroup a task.
    project_id: str | None = Field(..., min_length=1, max_length=100)


class MessageCreateRequest(BaseModel):
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
