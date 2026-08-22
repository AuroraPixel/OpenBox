"""Revoking one refresh token must not revoke everybody's.

The blacklist keyed on `token[:32]`, which is the base64 JWT header — byte
for byte identical for every token this service issues. One logout wrote a
key that matched every token of every user, so "remember me" stopped working
for the whole deployment until the entry expired, and nobody could stay
signed in across a browser restart.
"""
import pytest

from auth.routes import _blacklist_key


def test_two_tokens_get_two_keys():
    a = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaaaaaaaaaa.sigA"
    b = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.bbbbbbbbbbbb.sigB"
    assert a[:32] == b[:32]          # the bug's premise
    assert _blacklist_key(a) != _blacklist_key(b)


def test_the_same_token_gets_the_same_key():
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
    assert _blacklist_key(token) == _blacklist_key(token)


def test_the_key_does_not_carry_the_token():
    # It lands in a shared cache; a key that embeds the credential hands it
    # to anyone who can list keys.
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret-payload.sig"
    assert "secret-payload" not in _blacklist_key(token)


def test_real_tokens_for_two_users_differ():
    import os
    from auth.jwt import init_auth, create_refresh_token

    init_auth(os.getenv("JWT_SECRET") or "test-secret-for-unit-tests")
    a = create_refresh_token("userA")
    b = create_refresh_token("userB")
    assert a[:32] == b[:32]          # still true of the raw tokens
    assert _blacklist_key(a) != _blacklist_key(b)
