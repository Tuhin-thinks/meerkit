import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meerkit.services.instagram_gateway import extract_relationship_totals

GRAPHQL_USER_DATA = {
    "pk": "5165665016",
    "username": "me.between.waypoints",
    "is_private": False,
    "follower_count": 1135,
    "following_count": 1184,
    "mutual_followers_count": None,
    "friendship_status": None,
}


def test_extract_relationship_totals_from_modern_graphql_format():
    follower_count, following_count = extract_relationship_totals(GRAPHQL_USER_DATA)
    assert follower_count == 1135
    assert following_count == 1184


def test_extract_relationship_totals_from_legacy_rest_format():
    legacy = {
        "pk": "1",
        "account_followers_count": 10,
        "account_following_count": 20,
        "being_followed_by_account": True,
    }
    follower_count, following_count = extract_relationship_totals(legacy)
    assert follower_count == 10
    assert following_count == 20


def test_extract_relationship_totals_from_graphql_edge_format():
    edge = {
        "id": "1",
        "edge_followed_by": {"count": 100},
        "edge_follow": {"count": 50},
    }
    follower_count, following_count = extract_relationship_totals(edge)
    assert follower_count == 100
    assert following_count == 50


def test_extract_relationship_totals_missing_counts():
    follower_count, following_count = extract_relationship_totals({"pk": "1"})
    assert follower_count is None
    assert following_count is None


def test_extract_relationship_totals_does_not_fall_through_on_zero():
    zero = {"follower_count": 0, "following_count": 0}
    follower_count, following_count = extract_relationship_totals(zero)
    assert follower_count == 0
    assert following_count == 0
