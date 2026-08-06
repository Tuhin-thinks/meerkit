import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meerkit.services.instagram_gateway import InstagramGateway, ii


def _profile() -> ii.InstagramProfile:
    return ii.InstagramProfile(
        csrf_token="csrf",
        session_id="session",
        user_id="123",
    )


def _install_pages(monkeypatch, total_pages: int, page_size: int = 12):
    """Simulate an Instagram list endpoint serving ``total_pages`` pages of users."""

    def fake_pattern_call(self, **kwargs):
        runtime = kwargs.get("runtime_values") or {}
        if "max_id" in runtime:
            page_num = int(runtime["max_id"]) + 1
        else:
            page_num = 1
        start = (page_num - 1) * page_size
        users = [
            {"pk": str(start + i), "id": str(start + i)} for i in range(page_size)
        ]
        if page_num >= total_pages:
            return {"users": users}
        return {"users": users, "next_max_id": str(page_num)}

    monkeypatch.setattr(
        "meerkit.services.instagram_gateway.InstagramGateway._pattern_call",
        fake_pattern_call,
    )


def test_paginated_truncates_at_max_pages_without_expected_total(monkeypatch):
    gateway = InstagramGateway()
    _install_pages(monkeypatch, total_pages=10)

    result = gateway._pattern_call_paginated(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        internal_name="fetch_followers_list",
        profile=_profile(),
        max_pages=3,
        page_delay=0,
    )

    assert len(result["users"]) == 36


def test_paginated_exhausts_expected_total_beyond_initial_cap(monkeypatch):
    gateway = InstagramGateway()
    _install_pages(monkeypatch, total_pages=10)

    result = gateway._pattern_call_paginated(
        app_user_id="app_1",
        reference_profile_id="ig_1",
        internal_name="fetch_followers_list",
        profile=_profile(),
        max_pages=3,
        expected_total=120,
        page_delay=0,
    )

    assert len(result["users"]) == 120
