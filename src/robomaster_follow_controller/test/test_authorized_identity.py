from types import SimpleNamespace

from robomaster_follow_controller.follow_node import is_authorized_identity


AUTHORIZED_STATUSES = ("recognized", "cached")


def identity(name, status):
    return SimpleNamespace(name=name, status=status)


def test_recognized_identity_is_authorized():
    assert is_authorized_identity(
        identity("Himanshu", "recognized"),
        AUTHORIZED_STATUSES,
    )


def test_cached_identity_is_authorized():
    assert is_authorized_identity(identity("Himanshu", "cached"), AUTHORIZED_STATUSES)


def test_unknown_name_is_not_authorized_even_with_recognized_status():
    assert not is_authorized_identity(
        identity("unknown", "recognized"),
        AUTHORIZED_STATUSES,
    )


def test_unrecognized_status_is_not_authorized():
    assert not is_authorized_identity(
        identity("Himanshu", "below_threshold"),
        AUTHORIZED_STATUSES,
    )


def test_missing_identity_is_not_authorized():
    assert not is_authorized_identity(None, AUTHORIZED_STATUSES)
