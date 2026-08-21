"""Which browser the agent drives, per user.

Two very different browsers sit behind the dev-browser skill:

- ``local``  — Chrome on the cloud desktop. Always there, carries none of the
  user's logins.
- ``remote`` — the user's OWN Chrome, reached through the browser extension.
  Carries their real sessions, but only while the extension is connected.

``auto`` prefers the user's own browser and falls back to the cloud one the
moment the extension is gone, so a task does not die because someone closed a
window.

The preference lives in the existing per-user preferences row rather than a
table of its own. Note the vocabulary split: the product says ``remote``, the
relay's own config calls that same mode ``extension`` — `relay_mode` is the
single place that translation happens, so the two names never leak into each
other's territory.
"""
from db.repository.preference_repo import PgPreferenceRepo

#: Key inside UserPreference.extra.
PREF_KEY = "browser_mode"

MODES = ("auto", "local", "remote")
DEFAULT_MODE = "auto"


class InvalidBrowserMode(ValueError):
    pass


async def get_browser_mode(user_id: str) -> str:
    """The user's stored choice, defaulting to auto."""
    prefs = await PgPreferenceRepo().get(user_id)
    mode = ((prefs or {}).get("extra") or {}).get(PREF_KEY)
    return mode if mode in MODES else DEFAULT_MODE


async def set_browser_mode(user_id: str, mode: str) -> str:
    """Persist a choice. Raises InvalidBrowserMode on anything unexpected."""
    if mode not in MODES:
        raise InvalidBrowserMode(f"browser mode must be one of {', '.join(MODES)}, got {mode!r}")
    repo = PgPreferenceRepo()
    prefs = await repo.get(user_id)
    # Merge rather than replace: `extra` is a shared bag other settings use.
    extra = dict((prefs or {}).get("extra") or {})
    extra[PREF_KEY] = mode
    await repo.upsert(user_id, extra=extra)
    return mode


def relay_mode(mode: str) -> str:
    """Translate the product's vocabulary into the relay's."""
    return "extension" if mode == "remote" else mode
