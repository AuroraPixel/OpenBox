"""Question routes."""
from fastapi import APIRouter, Depends, HTTPException
from auth.middleware import get_current_user
from pydantic import BaseModel

from question import question as q_mod

router = APIRouter(dependencies=[Depends(get_current_user)])


class QuestionReplyBody(BaseModel):
    answers: list[list[str]]  # One string[] per question (selected labels)


@router.get("/question")
async def list_questions(current_user: dict = Depends(get_current_user)):
    """List all pending questions."""
    user_id = current_user["user_id"]
    return q_mod.list_pending(user_id=user_id)


@router.post("/question/{request_id}")
async def reply_question(
    request_id: str,
    body: QuestionReplyBody,
    current_user: dict = Depends(get_current_user),
):
    """Reply to a question from the AI."""
    user_id = current_user["user_id"]
    try:
        await q_mod.reply(request_id, body.answers, user_id=user_id)
    except KeyError:
        raise HTTPException(404, "Question request not found")
    except PermissionError:
        raise HTTPException(403, "Question request does not belong to current user")
    return {"ok": True}


@router.post("/question/{request_id}/reject")
async def reject_question(request_id: str, current_user: dict = Depends(get_current_user)):
    """Reject/dismiss a question from the AI."""
    user_id = current_user["user_id"]
    try:
        await q_mod.reject(request_id, user_id=user_id)
    except KeyError:
        raise HTTPException(404, "Question request not found")
    except PermissionError:
        raise HTTPException(403, "Question request does not belong to current user")
    return {"ok": True}
