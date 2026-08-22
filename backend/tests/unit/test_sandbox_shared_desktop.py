"""A pre-provisioned sandbox must survive being recycled.

The WUYING desktop is not OpenBox's container: it was provisioned out of
band and outlives the process. Recycling a sandbox that failed a liveness
check used to clear it from the provider's registry, and nothing outside
the provider's __init__ ever puts it back — so one bad health check turned
every later request into `KeyError: 'wuying-desktop'` until the server was
restarted.
"""
import pytest

from sandbox.wuying import CONTAINER_ID, WuyingProvider


@pytest.fixture
def provider(monkeypatch):
    return WuyingProvider()


def evict(p: WuyingProvider) -> None:
    """What _cleanup_stale_sandbox used to do to this provider."""
    p._containers.pop(CONTAINER_ID, None)
    p._api_keys.pop(CONTAINER_ID, None)


def test_the_desktop_is_there_to_begin_with(provider):
    assert provider.get_user_container("someone").id == CONTAINER_ID


def test_the_desktop_comes_back_after_being_evicted(provider):
    evict(provider)
    assert provider.get_user_container("someone").id == CONTAINER_ID


async def test_every_accessor_survives_an_eviction(provider):
    evict(provider)
    assert (await provider.get_container(CONTAINER_ID)).id == CONTAINER_ID
    assert (await provider.ensure_user_container("someone")).id == CONTAINER_ID
    assert (await provider.create_container("x")).id == CONTAINER_ID


def test_the_restored_entry_keeps_its_credentials(provider):
    before = provider.get_user_container("someone")
    evict(provider)
    after = provider.get_user_container("someone")
    assert (after.api_key, after.host, after.port) == (before.api_key, before.host, before.port)


def test_it_is_not_evictable_in_the_first_place():
    # The provider heals itself, but the caller should not be doing this at
    # all — a container it cannot recreate is not its to forget.
    assert WuyingProvider.owns_containers is False


def test_a_provider_that_makes_its_own_containers_still_forgets_them():
    from sandbox.docker import DockerManager
    assert DockerManager.owns_containers is True
