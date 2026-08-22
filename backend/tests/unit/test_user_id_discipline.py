"""Who a write or a delivery is for must be said, not defaulted.

Five bugs in this codebase came from the same shape: a `user_id` parameter
with a plausible-looking default of "default", and a caller that left it off.
The write then targeted a user nobody is, or the event was delivered to one —
silently, because "default" is a valid string.

The functions guarded here are the boundaries where that value decides who is
affected. They take user_id keyword-only and without a default, so omitting it
is a TypeError at the call, not a mystery in production.
"""
import inspect

import pytest

from sandbox.manager import SandboxManager
from session.session import save_part


def _param(fn, name):
    return inspect.signature(fn).parameters[name]


@pytest.mark.parametrize(
    "fn",
    [save_part, SandboxManager.get_client, SandboxManager.get_client_any, SandboxManager.acquire],
    ids=lambda f: f.__qualname__,
)
def test_user_id_has_no_default(fn):
    p = _param(fn, "user_id")
    assert p.default is inspect.Parameter.empty, (
        f"{fn.__qualname__} defaults user_id; a caller that forgets it will "
        "write or deliver to a user who does not exist"
    )


@pytest.mark.parametrize(
    "fn",
    [save_part, SandboxManager.get_client, SandboxManager.get_client_any, SandboxManager.acquire],
    ids=lambda f: f.__qualname__,
)
def test_user_id_is_keyword_only(fn):
    # Positionally it can be passed by accident in the wrong slot; by name it
    # cannot.
    assert _param(fn, "user_id").kind is inspect.Parameter.KEYWORD_ONLY


def test_save_part_refuses_to_be_called_without_one():
    with pytest.raises(TypeError):
        save_part(object())  # noqa: F821 — never awaited; the bind fails first


def test_the_maintenance_sweep_does_not_borrow_an_identity():
    # A deployment-wide sweep belongs to no user, so it asks for the only
    # sandbox rather than guessing whose to use.
    assert "user_id" not in inspect.signature(SandboxManager.get_only_client).parameters
