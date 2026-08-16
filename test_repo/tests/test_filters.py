"""Hidden FAIL_TO_PASS tests for search_engine.filters.PermissionFilter.

The agent must make public files accessible even when the user has no
user_id (anonymous sessions).
"""

from search_engine.filters import PermissionFilter


def test_anonymous_user_sees_public_files() -> None:
    pf = PermissionFilter()
    results = [("/public/doc.txt", "text", 0.9)]
    filtered = pf.filter_by_permissions(results, {"is_admin": False})
    assert filtered == results


def test_anonymous_user_sees_public_file_without_user_id_key() -> None:
    pf = PermissionFilter()
    results = [("/public/report.md", "markdown", 0.8)]
    filtered = pf.filter_by_permissions(results, {"is_admin": False})
    assert len(filtered) == 1
    assert filtered[0][0] == "/public/report.md"


def test_anonymous_user_still_blocked_from_private_files() -> None:
    pf = PermissionFilter()
    results = [("/users/u1/secret.txt", "text", 0.7)]
    filtered = pf.filter_by_permissions(results, {"is_admin": False})
    assert filtered == []
