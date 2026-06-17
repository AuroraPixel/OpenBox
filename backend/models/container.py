from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ContainerStatus(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class CreateContainerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    image: str = Field(default="openbox-sandbox:latest")
    project_id: str | None = Field(default=None, description="Project ID for persistent volumes")


class ContainerInfo(BaseModel):
    id: str
    name: str
    status: ContainerStatus
    image: str
    created_at: datetime
    host: str = "localhost"
    port: int | None = None
    api_key: str | None = None


class ContainerListResponse(BaseModel):
    containers: list[ContainerInfo]
    total: int


class ExecuteRequest(BaseModel):
    command: str
    timeout: int = 30


class ExecuteResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class ListFilesRequest(BaseModel):
    path: str = "/workspace"


class FileEntry(BaseModel):
    name: str
    is_dir: bool
    size: int | None = None
    modified: str | None = None


class SystemInfo(BaseModel):
    cpu: dict
    memory: dict
    disk: dict


class ErrorResponse(BaseModel):
    detail: str


class SuccessResponse(BaseModel):
    message: str


class ImageStatusResponse(BaseModel):
    exists: bool
    image: str
