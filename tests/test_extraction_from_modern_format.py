from meerkit.services.instagram_gateway import extract_friendship_flags, extract_relationship_totals

MODERN_GRAPHQL_FORMAT = {
    "pk": "65981764571",
    "username": "limba5294",
    "full_name": "Govind limba",
    "is_private": True,
    "is_verified": False,
    "follower_count": 9,
    "following_count": 3090,
    "mutual_followers_count": 0,
    "friendship_status": {
        "following": False,
        "followed_by": True,
        "blocking": False,
        "is_feed_favorite": False,
        "outgoing_request": False,
        "incoming_request": False,
        "is_restricted": False,
        "is_bestie": False,
        "muting": False,
        "is_muting_reel": False,
    },
}


def test_extract_friendship_flags_from_modern_graphql():
    me_following, followed_by = extract_friendship_flags(MODERN_GRAPHQL_FORMAT)
    assert me_following is False
    assert followed_by is True


def test_extract_relationship_totals_from_modern_graphql():
    follower_count, following_count = extract_relationship_totals(MODERN_GRAPHQL_FORMAT)
    assert follower_count == 9
    assert following_count == 3090
