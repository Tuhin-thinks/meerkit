import get_current_followers as scan_module
import insta_interface as ii


def _record(pk_id: str, username: str) -> ii.FollowerUserRecord:
    return ii.FollowerUserRecord(
        pk_id=pk_id,
        id=pk_id,
        profile_pic_url=f"https://img.example/{username}.jpg",
        username=username,
        full_name=username.title(),
        is_private=False,
        fbid_v2=None,
        profile_pic_id=None,
        is_verified=False,
    )


def test_run_scan_for_api_force_refreshes_current_relationships(monkeypatch, tmp_path):
    follower_records = [_record("1", "alice"), _record("2", "bob")]
    following_records = [_record("3", "carol")]
    refresh_calls: list[tuple[str, bool]] = []

    def capture_followers(**kwargs):
        refresh_calls.append(("followers", kwargs["force_refresh"]))
        return follower_records

    def capture_following(**kwargs):
        refresh_calls.append(("following", kwargs["force_refresh"]))
        return following_records

    monkeypatch.setattr(
        "get_current_followers.instagram_gateway.get_current_followers_v2",
        capture_followers,
    )
    monkeypatch.setattr(
        "get_current_followers.instagram_gateway.get_current_following_v2",
        capture_following,
    )
    monkeypatch.setattr("get_current_followers._load_latest_snapshot", lambda *_: None)
    monkeypatch.setattr(
        "get_current_followers.add_to_downloader_queue", lambda *args: None
    )
    monkeypatch.setattr(
        "get_current_followers.store_scan_info",
        lambda *args: "stored_scan_id",
    )
    monkeypatch.setattr(
        "get_current_followers.generate_scan_diff",
        lambda *args: "diff_123",
    )
    monkeypatch.setattr(
        "meerkit.services.account_handler.reconcile_followback_predictions",
        lambda **kwargs: 0,
    )

    result = scan_module.run_scan_for_api(
        app_user_id="app_1",
        data_dir=tmp_path,
        csrf_token="csrf",
        session_id="session",
        reference_profile_id="ig_1",
    )

    assert refresh_calls == [("followers", True), ("following", True)]
    assert result["diff_id"] == "diff_123"
    assert result["follower_count"] == len(follower_records)
