"""Project CRUD.

A project is the directory sessions run in, so these routes are what let a user
pick up an existing body of work instead of starting every conversation in an
empty folder.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.middleware import get_current_user
from core.log import create_logger
from project import workspace

log = create_logger("api.projects")

router = APIRouter()


class CreateProjectBody(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None


class UpdateProjectBody(BaseModel):
    name: str


@router.get("/project")
async def list_projects(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    # Guarantees the picker is never empty, even for a brand new account.
    await workspace.ensure_default_project(user_id)
    projects = await workspace.list_projects(user_id)
    counts = await workspace.session_counts(user_id)
    out = []
    for p in projects:
        p.session_count = counts.get(p.id, 0)
        out.append(p.to_dict())
    return out


@router.post("/project")
async def create_project(
    body: CreateProjectBody,
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["user_id"]
    try:
        project = await workspace.create_project(
            user_id, body.name, slug=body.slug, description=body.description
        )
    except workspace.ProjectError as e:
        raise HTTPException(400, str(e))

    # Best effort: the directory is also created on the path that starts a run,
    # so a sandbox that is down right now does not block creating the project.
    try:
        from sandbox import sandbox_manager
        client = await sandbox_manager.get_client_any(user_id=user_id)
        if client:
            await workspace.ensure_directory(client, project.slug)
    except Exception as e:
        log.debug(f"Deferred directory creation for {project.slug}: {e}")

    return project.to_dict()


@router.get("/project/{project_id}")
async def get_project(project_id: str, current_user: dict = Depends(get_current_user)):
    project = await workspace.get_project(project_id, current_user["user_id"])
    if not project:
        raise HTTPException(404, "Project not found")
    counts = await workspace.session_counts(current_user["user_id"])
    project.session_count = counts.get(project.id, 0)
    return project.to_dict()


@router.patch("/project/{project_id}")
async def update_project(
    project_id: str,
    body: UpdateProjectBody,
    current_user: dict = Depends(get_current_user),
):
    try:
        project = await workspace.rename_project(
            project_id, current_user["user_id"], body.name
        )
    except workspace.ProjectError as e:
        raise HTTPException(400, str(e))
    return project.to_dict()


@router.delete("/project/{project_id}")
async def delete_project(project_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    client = None
    try:
        from sandbox import sandbox_manager
        client = await sandbox_manager.get_client_any(user_id=user_id)
    except Exception as e:
        log.debug(f"No sandbox available while deleting {project_id}: {e}")
    try:
        await workspace.delete_project(project_id, user_id, sandbox=client)
    except workspace.ProjectError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}
