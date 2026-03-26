import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse

import insta_interface as ii
from backend.services import db_service, relationship_cache, user_details_cache
from backend.services.downloader import enqueue_image_download
from backend.services.instagram_gateway import instagram_gateway

_PREDICTION_TTL = timedelta(days=7)
_CACHE_FRESHNESS = timedelta(hours=6)
_HISTORICAL_REFERENCE_LIMIT = 400
_RELATIONSHIP_TYPES = {"followers", "following"}
_USER_ID_INPUT_PATTERN = re.compile(r"^\d+$")
_USERNAME_INPUT_PATTERN = re.compile(r"^[A-Za-z0-9._]+$")
_INSTAGRAM_PROFILE_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
_NON_PROFILE_ROUTE_PREFIXES = {
    "about",
    "accounts",
    "developer",
    "direct",
    "explore",
    "graphql",
    "p",
    "reel",
    "reels",
    "stories",
    "tv",
}


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _metadata_feature_subset(metadata: dict[str, object] | None) -> dict[str, object]:
    if not metadata:
        return {}
    return {
        "mutual_followers_count": _as_int(metadata.get("mutual_followers_count")),
        "media_count": _as_int(metadata.get("media_count")),
        "bio_links_count": _as_int(metadata.get("bio_links_count")),
        "category": _as_str(metadata.get("category")),
        "biography": _as_str(metadata.get("biography")),
        "account_type": _as_str(metadata.get("account_type")),
        "is_professional_account": _as_bool(metadata.get("is_professional_account")),
        "has_highlight_reels": _as_bool(metadata.get("has_highlight_reels")),
        "profile_pic_id": _as_str(metadata.get("profile_pic_id")),
        "profile_pic_url": _as_str(metadata.get("profile_pic_url")),
    }


def _latest_prediction_metadata(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
) -> dict[str, object] | None:
    latest_prediction = db_service.get_latest_prediction_for_target(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
    )
    if not latest_prediction:
        return None

    result_payload = latest_prediction.get("result_payload")
    if not isinstance(result_payload, dict):
        return None

    target_profile = result_payload.get("target_profile")
    if not isinstance(target_profile, dict):
        return None
    return target_profile


def _refresh_target_profile_image_cache_if_changed(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    previous_metadata: dict[str, object] | None,
    current_metadata: dict[str, object],
) -> None:
    previous_profile_pic_id = _as_str((previous_metadata or {}).get("profile_pic_id"))
    current_profile_pic_id = _as_str(current_metadata.get("profile_pic_id"))
    current_profile_pic_url = _as_str(current_metadata.get("profile_pic_url"))
    if not (
        previous_profile_pic_id
        and current_profile_pic_id
        and current_profile_pic_url
        and previous_profile_pic_id != current_profile_pic_id
    ):
        return
    enqueue_image_download(
        app_user_id=app_user_id,
        instagram_user_id=reference_profile_id,
        profile_pk_id=target_profile_id,
        profile_pic_url=current_profile_pic_url,
    )


def _build_profile(credentials: dict) -> ii.InstagramProfile:
    return ii.InstagramProfile(
        csrf_token=credentials["csrf_token"],
        session_id=credentials["session_id"],
        user_id=credentials["user_id"],
    )


def _extract_username_from_target_input(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None

    if "instagram.com" not in normalized.lower():
        return normalized.lstrip("@").strip() or None

    candidate = normalized
    if "://" not in candidate:
        candidate = f"https://{candidate.lstrip('/')}"

    parsed = urlparse(candidate)
    if parsed.netloc and parsed.netloc.lower() not in _INSTAGRAM_PROFILE_HOSTS:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None

    username = path_parts[0].lstrip("@").strip()
    if not username or username.lower() in _NON_PROFILE_ROUTE_PREFIXES:
        return None
    return username


def _normalize_prediction_target_input(
    username: str | None,
    user_id: str | None,
) -> tuple[str | None, str | None]:
    normalized_user_id = (user_id or "").strip() or None
    if normalized_user_id:
        return None, normalized_user_id

    extracted_username = _extract_username_from_target_input(username or "")
    if not extracted_username:
        return None, None
    if _USER_ID_INPUT_PATTERN.fullmatch(extracted_username):
        return None, extracted_username
    if not _USERNAME_INPUT_PATTERN.fullmatch(extracted_username):
        return None, None
    return extracted_username, None


def _is_fresh(timestamp: str | None, ttl: timedelta = _CACHE_FRESHNESS) -> bool:
    if not timestamp:
        return False
    try:
        return datetime.now() - datetime.fromisoformat(timestamp) <= ttl
    except ValueError:
        return False


def _cache_ready(
    app_user_id: str, reference_profile_id: str, target_profile_id: str
) -> bool:
    target_profile = db_service.get_target_profile(
        app_user_id, reference_profile_id, target_profile_id
    )
    if not target_profile:
        return False
    if target_profile.get("fetch_status") not in {"ready", "partial", "metadata_only"}:
        return False
    return _is_fresh(target_profile.get("metadata_fetched_at"))


def _normalize_relationship_types(relationship_type: str | None) -> set[str]:
    if relationship_type is None:
        return set(_RELATIONSHIP_TYPES)
    normalized = relationship_type.strip().lower()
    if normalized not in _RELATIONSHIP_TYPES:
        raise ValueError("relationship_type must be either 'followers' or 'following'")
    return {normalized}


def _count_for_relationship_type(
    relationship_type: str,
    follower_count: int | None,
    following_count: int | None,
) -> int | None:
    return follower_count if relationship_type == "followers" else following_count


def _invalidate_relationship_cache_entry(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    relationship_type: str,
    reason: str,
    invalidated_at: str | None = None,
) -> bool:
    active_entry = db_service.get_active_target_profile_list_cache_entry(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        relationship_type=relationship_type,
    )
    if not active_entry:
        return False

    relationship_cache.delete_cache_file(active_entry.get("cache_file_path"))
    db_service.invalidate_target_profile_list_cache_entry(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        relationship_type=relationship_type,
        reason=reason,
        invalidated_at=invalidated_at,
    )
    return True


def _invalidate_changed_count_caches(
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    follower_count: int | None,
    following_count: int | None,
    invalidated_at: str | None = None,
) -> set[str]:
    changed_types: set[str] = set()
    for relationship_type in _RELATIONSHIP_TYPES:
        active_entry = db_service.get_active_target_profile_list_cache_entry(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            relationship_type=relationship_type,
        )
        if not active_entry:
            continue

        source_count = active_entry.get("source_count_at_fetch")
        current_count = _count_for_relationship_type(
            relationship_type=relationship_type,
            follower_count=follower_count,
            following_count=following_count,
        )
        if (
            isinstance(source_count, int)
            and isinstance(current_count, int)
            and source_count != current_count
        ):
            _invalidate_relationship_cache_entry(
                app_user_id=app_user_id,
                reference_profile_id=reference_profile_id,
                target_profile_id=target_profile_id,
                relationship_type=relationship_type,
                reason="count_changed",
                invalidated_at=invalidated_at,
            )
            changed_types.add(relationship_type)
    return changed_types


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _safe_ratio(numerator: int | None, denominator: int | None) -> float:
    if numerator is None or denominator is None or denominator <= 0:
        return 0.0
    return numerator / denominator


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _logit(probability: float) -> float:
    bounded = _clamp(probability, 1e-5, 1 - 1e-5)
    return math.log(bounded / (1 - bounded))


def _bucket_count(value: int | None) -> str:
    if value is None:
        return "unknown"
    if value < 500:
        return "tiny"
    if value < 2_000:
        return "small"
    if value < 10_000:
        return "mid"
    if value < 100_000:
        return "large"
    return "massive"


def _bucket_ratio(value: float) -> str:
    if value <= 0:
        return "none"
    if value < 0.02:
        return "very_low"
    if value < 0.08:
        return "low"
    if value < 0.2:
        return "medium"
    return "high"


def _bucket_overlap_count(value: int) -> str:
    if value <= 0:
        return "none"
    if value <= 2:
        return "low"
    if value <= 8:
        return "medium"
    return "high"


def _build_feature_breakdown(
    target_profile: dict | None,
    metadata_features: dict[str, object],
    latest_follower_ids: set[str],
    target_followers: set[str],
    target_following: set[str],
    overlap_followers: int,
    overlap_following: int,
    alt_followback_assessment: dict[str, object] | None = None,
) -> dict[str, object]:
    follower_count = (
        _as_int(target_profile.get("follower_count")) if target_profile else None
    )
    following_count = (
        _as_int(target_profile.get("following_count")) if target_profile else None
    )
    mutual_followers_count = _as_int(metadata_features.get("mutual_followers_count"))

    following_to_follower_ratio = _safe_ratio(following_count, follower_count)
    mutual_to_follower_ratio = _safe_ratio(mutual_followers_count, follower_count)
    overlap_followers_to_reference_ratio = _safe_ratio(
        overlap_followers, len(latest_follower_ids)
    )
    overlap_following_to_reference_ratio = _safe_ratio(
        overlap_following, len(latest_follower_ids)
    )
    overlap_followers_to_target_ratio = _safe_ratio(
        overlap_followers, len(target_followers)
    )
    overlap_following_to_target_ratio = _safe_ratio(
        overlap_following, len(target_following)
    )

    graph_fetch_status = "metadata_only"
    if target_followers and target_following:
        graph_fetch_status = "ready"
    elif target_followers or target_following:
        graph_fetch_status = "partial"

    breakdown = {
        "audience_overlap_followers": overlap_followers,
        "audience_overlap_following": overlap_following,
        "audience_overlap_followers_ratio_reference": round(
            overlap_followers_to_reference_ratio, 4
        ),
        "audience_overlap_following_ratio_reference": round(
            overlap_following_to_reference_ratio, 4
        ),
        "audience_overlap_followers_ratio_target": round(
            overlap_followers_to_target_ratio, 4
        ),
        "audience_overlap_following_ratio_target": round(
            overlap_following_to_target_ratio, 4
        ),
        "is_private": target_profile.get("is_private") if target_profile else None,
        "is_verified": target_profile.get("is_verified") if target_profile else None,
        "me_following_account": target_profile.get("me_following_account")
        if target_profile
        else None,
        "being_followed_by_account": target_profile.get("being_followed_by_account")
        if target_profile
        else None,
        "already_follows_account": bool(
            target_profile.get("being_followed_by_account") if target_profile else False
        ),
        "follower_count": follower_count,
        "following_count": following_count,
        "following_to_follower_ratio": round(following_to_follower_ratio, 4),
        "mutual_to_follower_ratio": round(mutual_to_follower_ratio, 4),
        "target_size_bucket": _bucket_count(follower_count),
        "mutual_bucket": _bucket_overlap_count(mutual_followers_count or 0),
        "overlap_followers_bucket": _bucket_overlap_count(overlap_followers),
        "overlap_following_bucket": _bucket_overlap_count(overlap_following),
        "overlap_followers_ratio_bucket": _bucket_ratio(
            overlap_followers_to_reference_ratio
        ),
        "overlap_following_ratio_bucket": _bucket_ratio(
            overlap_following_to_reference_ratio
        ),
        "graph_fetch_status": graph_fetch_status,
        **metadata_features,
    }
    if alt_followback_assessment:
        matched_alt_keys = alt_followback_assessment.get("matched_alt_identity_keys")
        if not isinstance(matched_alt_keys, list):
            matched_alt_keys = []
        breakdown["has_alt_account_followback"] = bool(
            alt_followback_assessment.get("is_alt_account_following_you")
        )
        breakdown["alt_account_followback_count"] = len(matched_alt_keys)
    else:
        breakdown["has_alt_account_followback"] = False
        breakdown["alt_account_followback_count"] = 0
    return breakdown


def _historical_cohort_keys(feature_breakdown: dict[str, object]) -> tuple[str, ...]:
    return (
        f"size:{feature_breakdown.get('target_size_bucket')}",
        f"private:{feature_breakdown.get('is_private')}",
        f"professional:{feature_breakdown.get('is_professional_account')}",
        f"verified:{feature_breakdown.get('is_verified')}",
        f"mutual:{feature_breakdown.get('mutual_bucket')}",
        f"overlap_followers:{feature_breakdown.get('overlap_followers_bucket')}",
        f"overlap_following:{feature_breakdown.get('overlap_following_bucket')}",
        f"graph:{feature_breakdown.get('graph_fetch_status')}",
        f"me_following:{feature_breakdown.get('me_following_account')}",
    )


def _compute_historical_reference(
    app_user_id: str,
    reference_profile_id: str,
    feature_breakdown: dict[str, object],
) -> dict[str, float | int]:
    history = db_service.list_labeled_followback_predictions(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        limit=_HISTORICAL_REFERENCE_LIMIT,
    )

    usable_rows: list[dict] = []
    positive_count = 0
    for row in history:
        if row.get("outcome_status") not in {"correct", "wrong"}:
            continue
        historical_breakdown = row.get("feature_breakdown")
        if not isinstance(historical_breakdown, dict):
            continue
        if historical_breakdown.get("being_followed_by_account"):
            continue
        usable_rows.append(row)
        if row.get("outcome_status") == "correct":
            positive_count += 1

    sample_count = len(usable_rows)
    if sample_count == 0:
        return {
            "sample_count": 0,
            "global_rate": 0.32,
            "calibrated_probability": 0.32,
        }

    global_prior_strength = 8.0
    global_rate = (positive_count + 2.0) / (sample_count + 4.0)
    matched_rates: list[tuple[float, float]] = []
    target_keys = _historical_cohort_keys(feature_breakdown)
    for key in target_keys:
        wins = 0
        total = 0
        for row in usable_rows:
            historical_breakdown = row.get("feature_breakdown")
            if not isinstance(historical_breakdown, dict):
                continue
            if key not in _historical_cohort_keys(historical_breakdown):
                continue
            total += 1
            if row.get("outcome_status") == "correct":
                wins += 1
        if total == 0:
            continue
        posterior = (wins + global_rate * global_prior_strength) / (
            total + global_prior_strength
        )
        weight = min(1.0, total / 24.0)
        matched_rates.append((posterior, weight))

    if matched_rates:
        weighted_sum = sum(rate * weight for rate, weight in matched_rates)
        weight_total = sum(weight for _, weight in matched_rates)
        calibrated_probability = weighted_sum / weight_total
    else:
        calibrated_probability = global_rate

    return {
        "sample_count": sample_count,
        "global_rate": round(global_rate, 4),
        "calibrated_probability": round(calibrated_probability, 4),
    }


@dataclass
class FollowbackComputationContext:
    app_user_id: str
    reference_profile_id: str
    target_profile_id: str
    include_overlap: bool
    target_profile: dict | None
    metadata_features: dict[str, object]
    latest_follower_ids: set[str]
    target_followers: set[str]
    target_following: set[str]
    overlap_followers: int
    overlap_following: int
    alt_followback_assessment: dict[str, object]
    feature_breakdown: dict[str, object]


@dataclass
class FollowbackMathResult:
    probability: float
    confidence: float
    reasons: list[str]
    historical_reference: dict[str, float | int]


def _assess_alt_account_followback(
    *,
    app_user_id: str,
    reference_profile_id: str,
    target_profile_id: str,
    target_profile: dict | None,
    target_followers: set[str],
) -> dict[str, object]:
    primary_identity_keys: set[str] = {target_profile_id}
    username = _as_str((target_profile or {}).get("username"))
    if username:
        primary_identity_keys.add(username)

    link_rows = db_service.list_alt_account_links_for_primary_keys(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        primary_identity_keys=primary_identity_keys,
    )
    if not link_rows:
        return {
            "is_alt_account_following_you": False,
            "matched_alt_identity_keys": [],
            "matched_alt_usernames": [],
            "linked_alt_count": 0,
        }

    cached_target_followers = (
        target_followers
        or db_service.get_target_profile_relationship_ids(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            relationship_type="followers",
        )
    )

    matched_alt_identity_keys: list[str] = []
    matched_alt_usernames: list[str] = []
    for link in link_rows:
        alt_identity_key = link.get("alt_identity_key")
        if not isinstance(alt_identity_key, str):
            continue
        if alt_identity_key not in cached_target_followers:
            continue
        matched_alt_identity_keys.append(alt_identity_key)
        alt_username = link.get("alt_normalized_username") or alt_identity_key
        if isinstance(alt_username, str):
            matched_alt_usernames.append(alt_username)

    matched_alt_identity_keys = sorted(set(matched_alt_identity_keys))
    matched_alt_usernames = sorted(set(matched_alt_usernames))
    linked_alt_count = len(
        {
            row.get("alt_identity_key")
            for row in link_rows
            if isinstance(row.get("alt_identity_key"), str)
        }
    )
    return {
        "is_alt_account_following_you": bool(matched_alt_identity_keys),
        "matched_alt_identity_keys": matched_alt_identity_keys,
        "matched_alt_usernames": matched_alt_usernames,
        "linked_alt_count": linked_alt_count,
    }


def _load_followback_computation_context(
    pk_id: str,
    reference_profile_id: str,
    app_user_id: str,
    metadata: dict[str, object] | None,
    include_overlap: bool,
) -> FollowbackComputationContext:
    target_profile = db_service.get_target_profile(
        app_user_id, reference_profile_id, pk_id
    )
    if include_overlap:
        latest_follower_ids = db_service.get_latest_scanned_profile_ids(
            app_user_id, reference_profile_id
        )
        target_followers = db_service.get_target_profile_relationship_ids(
            app_user_id, reference_profile_id, pk_id, "followers"
        )
        target_following = db_service.get_target_profile_relationship_ids(
            app_user_id, reference_profile_id, pk_id, "following"
        )
    else:
        latest_follower_ids = set()
        target_followers = set()
        target_following = set()

    metadata_features = _metadata_feature_subset(metadata)
    overlap_followers = len(target_followers & latest_follower_ids)
    overlap_following = len(target_following & latest_follower_ids)
    alt_followback_assessment = _assess_alt_account_followback(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=pk_id,
        target_profile=target_profile,
        target_followers=target_followers,
    )
    feature_breakdown = _build_feature_breakdown(
        target_profile=target_profile,
        metadata_features=metadata_features,
        latest_follower_ids=latest_follower_ids,
        target_followers=target_followers,
        target_following=target_following,
        overlap_followers=overlap_followers,
        overlap_following=overlap_following,
        alt_followback_assessment=alt_followback_assessment,
    )

    return FollowbackComputationContext(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=pk_id,
        include_overlap=include_overlap,
        target_profile=target_profile,
        metadata_features=metadata_features,
        latest_follower_ids=latest_follower_ids,
        target_followers=target_followers,
        target_following=target_following,
        overlap_followers=overlap_followers,
        overlap_following=overlap_following,
        alt_followback_assessment=alt_followback_assessment,
        feature_breakdown=feature_breakdown,
    )


def _calculate_followback_math(
    context: FollowbackComputationContext,
) -> FollowbackMathResult:
    score = _logit(0.28)
    confidence = 0.24
    reasons: list[str] = []

    target_profile = context.target_profile
    if target_profile:
        confidence += 0.14
        if target_profile.get("being_followed_by_account"):
            score = max(score, _logit(0.82))
            confidence += 0.12
            reasons.append("Target already follows the active account")
        if target_profile.get("me_following_account"):
            score += 0.2
            reasons.append("Active account already follows the target")
        if target_profile.get("is_private"):
            score -= 0.28
            reasons.append("Private account lowers likelihood of follow-back")
        else:
            score += 0.06
        if target_profile.get("is_verified"):
            score -= 0.38
            reasons.append("Verified accounts are less likely to follow back")

        follower_count = target_profile.get("follower_count")
        if isinstance(follower_count, int) and follower_count > 0:
            # Continuous log-scale adjustment: smaller accounts are more likely to follow back
            fc_adj = max(-0.42, min(0.22, 0.796 - 0.215 * math.log10(follower_count)))
            score += fc_adj
            if fc_adj > 0.05:
                reasons.append("Smaller audience size increases follow-back odds")
            elif fc_adj < -0.10:
                reasons.append("Large audience size lowers follow-back odds")

        following_count = _as_int(target_profile.get("following_count"))
        if (
            following_count is not None
            and isinstance(follower_count, int)
            and follower_count > 0
        ):
            # Higher following-to-follower ratio generally indicates reciprocal behavior.
            r = min(_safe_ratio(following_count, follower_count), 6.0)
            ratio_adj = 0.21 * math.tanh(2.5 * (r - 0.35))
            score += ratio_adj
            if ratio_adj >= 0.10:
                reasons.append(
                    "Following count close to follower count suggests reciprocal behavior"
                )
            elif ratio_adj <= -0.08:
                reasons.append(
                    "Very low following-to-follower ratio reduces follow-back likelihood"
                )

            raw_ratio = _safe_ratio(following_count, follower_count)
            if raw_ratio > 1.0:
                ratio_surplus = raw_ratio - 1.0
                high_ratio_bonus = min(
                    0.92, 0.18 * (math.exp(1.2 * ratio_surplus) - 1.0)
                )
                score += high_ratio_bonus
                if high_ratio_bonus >= 0.22:
                    reasons.append(
                        "High following-to-follower ratio strongly increases follow-back likelihood"
                    )
            elif raw_ratio < 1.0:
                follower_dominance = (1.0 / max(raw_ratio, 0.01)) - 1.0
                dominant_penalty = min(
                    2.8,
                    0.22 * (math.exp(1.35 * follower_dominance) - 1.0),
                )
                score -= dominant_penalty
                confidence += 0.05
                reasons.append(
                    "More followers than following critically lowers follow-back likelihood"
                )

    if context.alt_followback_assessment.get("is_alt_account_following_you"):
        score += 0.26
        confidence += 0.04
        reasons.append(
            "A linked alternative account already follows the active account"
        )

    mutual_followers_count = _as_int(
        context.metadata_features.get("mutual_followers_count")
    )
    if isinstance(mutual_followers_count, int) and mutual_followers_count > 0:
        # Keep mutuals as a weak supporting feature rather than a dominant signal.
        score += min(0.22, mutual_followers_count * 0.02)
        confidence += min(0.08, 0.02 + mutual_followers_count * 0.006)
        reasons.append(
            "Mutual followers increase likelihood of follow-back (small effect)"
        )

    mutual_to_follower_ratio = _safe_ratio(
        mutual_followers_count,
        _as_int(target_profile.get("follower_count")) if target_profile else None,
    )
    if mutual_to_follower_ratio >= 0.03:
        score += min(0.12, mutual_to_follower_ratio * 1.2)
        reasons.append("Mutual follower ratio adds slight audience overlap context")

    media_count = _as_int(context.metadata_features.get("media_count"))
    if isinstance(media_count, int) and media_count >= 1000:
        score -= 0.16
        reasons.append("Very high media volume slightly lowers follow-back odds")

    category = (_as_str(context.metadata_features.get("category")) or "").lower()
    if category and any(
        token in category
        for token in ("artist", "public figure", "creator", "celebrity", "musician")
    ):
        score -= 0.18
        reasons.append("Public-figure style categories reduce follow-back odds")

    if context.metadata_features.get("is_professional_account"):
        score -= 0.14
        reasons.append("Professional accounts are slightly less likely to follow back")

    biography = _as_str(context.metadata_features.get("biography")) or ""
    if biography and len(biography) >= 80:
        confidence += 0.03

    if context.metadata_features.get("has_highlight_reels"):
        confidence += 0.02

    if context.include_overlap:
        if context.overlap_followers:
            score += min(0.5, context.overlap_followers * 0.05)
            confidence += 0.1
            reasons.append("Target followers overlap with the active audience")
        if context.overlap_following:
            score += min(0.42, context.overlap_following * 0.04)
            confidence += 0.08
            reasons.append("Target following overlaps with the active audience")

        overlap_followers_ratio = _safe_ratio(
            context.overlap_followers, len(context.latest_follower_ids)
        )
        if overlap_followers_ratio >= 0.01:
            score += min(0.35, overlap_followers_ratio * 5.0)

        overlap_following_ratio = _safe_ratio(
            context.overlap_following, len(context.latest_follower_ids)
        )
        if overlap_following_ratio >= 0.01:
            score += min(0.28, overlap_following_ratio * 4.0)

        if context.target_followers or context.target_following:
            confidence += 0.16

    probability = _sigmoid(score)
    historical_reference = _compute_historical_reference(
        app_user_id=context.app_user_id,
        reference_profile_id=context.reference_profile_id,
        feature_breakdown=context.feature_breakdown,
    )
    history_weight = min(
        0.5,
        (float(historical_reference["sample_count"]) / 120.0) * 0.5,
    )
    probability = (
        probability * (1 - history_weight)
        + float(historical_reference["calibrated_probability"]) * history_weight
    )
    if history_weight > 0:
        reasons.append(
            "Historical confirmed outcomes were used to calibrate this score"
        )
    if float(historical_reference["sample_count"]) >= 20:
        confidence += min(0.16, float(historical_reference["sample_count"]) / 250.0)

    probability = _clamp(round(probability, 4), 0.03, 0.97)
    confidence = _clamp(round(confidence, 4))
    if not reasons:
        reasons.append(
            "Limited data available; prediction based on baseline heuristics"
        )

    return FollowbackMathResult(
        probability=probability,
        confidence=confidence,
        reasons=reasons,
        historical_reference=historical_reference,
    )


def compute_followback_chances(
    pk_id: str,
    reference_profile_id: str,
    app_user_id: str | None = None,
    metadata: dict[str, object] | None = None,
    include_overlap: bool = True,
):
    """Compute follow-back probability for one target user using cached profile data."""
    if not app_user_id:
        raise ValueError("app_user_id is required to compute followback chances")
    context = _load_followback_computation_context(
        pk_id=pk_id,
        reference_profile_id=reference_profile_id,
        app_user_id=app_user_id,
        metadata=metadata,
        include_overlap=include_overlap,
    )
    math_result = _calculate_followback_math(context)

    # Compute state flags
    graph_fetch_status = context.feature_breakdown["graph_fetch_status"]
    overlap_data_fetched = graph_fetch_status == "ready"
    overlap_available = context.include_overlap
    overlap_scoring_used = context.include_overlap
    ambiguous_probability = 0.45 <= math_result.probability <= 0.65
    can_fetch_overlap = not overlap_data_fetched

    return {
        "target_profile_id": pk_id,
        "target_username": context.target_profile.get("username")
        if context.target_profile
        else None,
        "followback_probability": math_result.probability,
        "confidence": math_result.confidence,
        "matched_followers_count": context.overlap_followers,
        "matched_following_count": context.overlap_following,
        "graph_fetch_status": graph_fetch_status,
        "used_cached_followers": bool(context.target_followers),
        "used_cached_following": bool(context.target_following),
        "used_fresh_fetch": False,
        "statistical_reference_count": math_result.historical_reference["sample_count"],
        "statistical_reference_rate": math_result.historical_reference[
            "calibrated_probability"
        ],
        "global_historical_rate": math_result.historical_reference["global_rate"],
        "overlap_data_fetched": overlap_data_fetched,
        "overlap_scoring_used": overlap_scoring_used,
        "overlap_available": overlap_available,
        "ambiguous_probability": ambiguous_probability,
        "can_fetch_overlap": can_fetch_overlap,
        "alt_followback_assessment": context.alt_followback_assessment,
        "feature_breakdown": context.feature_breakdown,
        "reasons": math_result.reasons,
    }


def request_followback_prediction(
    app_user_id: str,
    instagram_user: dict,
    username: str | None = None,
    user_id: str | None = None,
    refresh: bool = False,
    force_background: bool = False,
    relationship_type: str | None = None,
) -> dict:
    username, user_id = _normalize_prediction_target_input(username, user_id)
    if not username and not user_id:
        raise ValueError("username, profile link, or user_id is required")

    profile = _build_profile(instagram_user)
    target_profile_id = user_id or instagram_gateway.resolve_target_user_pk(
        app_user_id=app_user_id,
        instagram_user_id=instagram_user["instagram_user_id"],
        profile=profile,
        username=username or "",
        caller_service="account_handler",
        caller_method="request_followback_prediction",
    )
    if not target_profile_id:
        raise ValueError("Could not resolve target instagram user")

    cached_profile = db_service.get_target_profile(
        app_user_id, instagram_user["instagram_user_id"], target_profile_id
    )
    target_username = username or (cached_profile or {}).get("username")
    current_time = datetime.now().isoformat()
    expires_at = (datetime.now() + _PREDICTION_TTL).isoformat()
    requested_relationship_type = None
    if relationship_type is not None:
        requested_relationship_type = next(
            iter(_normalize_relationship_types(relationship_type))
        )

    if (
        not refresh
        and not force_background
        and _cache_ready(
            app_user_id, instagram_user["instagram_user_id"], target_profile_id
        )
    ):
        relationship_cache_summary = (
            db_service.get_target_profile_relationship_cache_summary(
                app_user_id=app_user_id,
                reference_profile_id=instagram_user["instagram_user_id"],
                target_profile_id=target_profile_id,
            )
        )
        has_full_overlap_cache = all(
            bool(item.get("active_file_present"))
            for item in relationship_cache_summary.values()
        )
        cached_metadata = _latest_prediction_metadata(
            app_user_id=app_user_id,
            reference_profile_id=instagram_user["instagram_user_id"],
            target_profile_id=target_profile_id,
        )
        result = compute_followback_chances(
            pk_id=target_profile_id,
            reference_profile_id=instagram_user["instagram_user_id"],
            app_user_id=app_user_id,
            metadata=cached_metadata,
            include_overlap=has_full_overlap_cache,
        )
        result["relationship_cache"] = relationship_cache_summary
        if cached_metadata:
            result["target_profile"] = {
                "username": target_username,
                "full_name": cached_metadata.get("full_name"),
                "follower_count": cached_profile.get("follower_count")
                if cached_profile
                else None,
                "following_count": cached_profile.get("following_count")
                if cached_profile
                else None,
                **_metadata_feature_subset(cached_metadata),
            }
        prediction = db_service.create_prediction(
            prediction_type="follow_back",
            app_user_id=app_user_id,
            reference_profile_id=instagram_user["instagram_user_id"],
            target_profile_id=target_profile_id,
            target_username=target_username,
            probability=result["followback_probability"],
            confidence=result["confidence"],
            status="completed",
            result_payload=result,
            feature_breakdown=result["feature_breakdown"],
            requested_at=current_time,
            computed_at=current_time,
            data_as_of=current_time,
            expires_at=expires_at,
        )
        return {"prediction": prediction, "task": None}

    from backend.services import prediction_runner

    active_task_bundle = prediction_runner.get_active_task_bundle(
        app_user_id=app_user_id,
        reference_profile_id=instagram_user["instagram_user_id"],
        target_profile_id=target_profile_id,
    )
    if active_task_bundle:
        return active_task_bundle

    prediction = db_service.create_prediction(
        prediction_type="follow_back",
        app_user_id=app_user_id,
        reference_profile_id=instagram_user["instagram_user_id"],
        target_profile_id=target_profile_id,
        target_username=target_username,
        status="queued",
        requested_at=current_time,
        expires_at=expires_at,
    )

    task = prediction_runner.enqueue_prediction_refresh(
        prediction_id=prediction["prediction_id"],
        app_user_id=app_user_id,
        reference_profile_id=instagram_user["instagram_user_id"],
        target_profile_id=target_profile_id,
        instagram_user=instagram_user,
        refresh_requested=refresh or force_background,
        relationship_type=requested_relationship_type,
        fetch_relationships=refresh or relationship_type is not None,
    )
    prediction = (
        db_service.update_prediction(
            prediction["prediction_id"],
            task_id=task["task_id"],
            status="queued",
        )
        or prediction
    )
    return {"prediction": prediction, "task": task}


def refresh_followback_prediction(
    prediction_id: str,
    instagram_user: dict,
    relationship_type: str | None = None,
    fetch_relationships: bool = True,
) -> dict:
    prediction = db_service.get_prediction(prediction_id)
    if not prediction:
        raise ValueError("Prediction not found")

    profile = _build_profile(instagram_user)
    target_profile_id = prediction["target_profile_id"]
    reference_profile_id = prediction["reference_profile_id"]
    app_user_id = prediction["app_user_id"]
    previous_target_metadata = user_details_cache.load_target(
        app_user_id,
        reference_profile_id,
        target_profile_id,
    )

    metadata = instagram_gateway.get_target_user_data(
        app_user_id=app_user_id,
        instagram_user_id=reference_profile_id,
        profile=profile,
        target_user_id=target_profile_id,
        caller_service="account_handler",
        caller_method="refresh_followback_prediction",
        force_refresh=True,
    )
    _refresh_target_profile_image_cache_if_changed(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        previous_metadata=previous_target_metadata,
        current_metadata=metadata,
    )
    metadata_time = datetime.now().isoformat()
    metadata_username = _as_str(metadata.get("username"))
    metadata_full_name = _as_str(metadata.get("full_name"))
    metadata_follower_count = _as_int(metadata.get("account_followers_count"))
    metadata_following_count = _as_int(metadata.get("account_following_count"))
    db_service.upsert_target_profile(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        username=metadata_username,
        full_name=metadata_full_name,
        follower_count=metadata_follower_count,
        following_count=metadata_following_count,
        is_private=bool(metadata.get("is_private", False)),
        is_verified=bool(metadata.get("is_verified", False)),
        me_following_account=bool(metadata.get("me_following_account", False)),
        being_followed_by_account=bool(
            metadata.get("being_followed_by_account", False)
        ),
        fetch_status="metadata_only",
        metadata_fetched_at=metadata_time,
        last_error=None,
    )

    relationships_time = datetime.now().isoformat()
    requested_relationships = _normalize_relationship_types(relationship_type)
    count_changed_relationships = _invalidate_changed_count_caches(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        follower_count=metadata_follower_count,
        following_count=metadata_following_count,
        invalidated_at=relationships_time,
    )
    relationships_to_refresh = requested_relationships | count_changed_relationships

    fetch_status = "ready"
    last_error: str | None = None

    if fetch_relationships:
        fetch_map = {
            "followers": lambda target_id: instagram_gateway.get_target_followers_v2(
                app_user_id=app_user_id,
                instagram_user_id=reference_profile_id,
                profile=profile,
                target_user_id=target_id,
                caller_service="account_handler",
                caller_method="refresh_followback_prediction",
                force_refresh=True,
            ),
            "following": lambda target_id: instagram_gateway.get_target_following_v2(
                app_user_id=app_user_id,
                instagram_user_id=reference_profile_id,
                profile=profile,
                target_user_id=target_id,
                caller_service="account_handler",
                caller_method="refresh_followback_prediction",
                force_refresh=True,
            ),
        }
        for relationship in sorted(relationships_to_refresh):
            try:
                records = fetch_map[relationship](target_profile_id)
                db_service.replace_target_profile_relationships(
                    app_user_id=app_user_id,
                    reference_profile_id=reference_profile_id,
                    target_profile_id=target_profile_id,
                    relationship_type=relationship,
                    profiles=records,
                    fetched_at=relationships_time,
                )
                _invalidate_relationship_cache_entry(
                    app_user_id=app_user_id,
                    reference_profile_id=reference_profile_id,
                    target_profile_id=target_profile_id,
                    relationship_type=relationship,
                    reason="replaced_by_new_fetch",
                    invalidated_at=relationships_time,
                )
                cache_file_path = relationship_cache.write_relationship_cache_file(
                    app_user_id=app_user_id,
                    reference_profile_id=reference_profile_id,
                    target_profile_id=target_profile_id,
                    relationship_type=relationship,
                    fetched_at=relationships_time,
                    profiles_payload=[asdict(item) for item in records],
                )
                db_service.create_target_profile_list_cache_entry(
                    app_user_id=app_user_id,
                    reference_profile_id=reference_profile_id,
                    target_profile_id=target_profile_id,
                    relationship_type=relationship,
                    cache_file_path=cache_file_path,
                    fetched_at=relationships_time,
                    source_count_at_fetch=_count_for_relationship_type(
                        relationship,
                        metadata_follower_count,
                        metadata_following_count,
                    ),
                )
            except Exception as exc:
                fetch_status = "partial"
                last_error = str(exc)
    else:
        # Skip relationship fetching; status remains "metadata_only" until relationships are fetched
        fetch_status = "metadata_only"

    cache_summary = db_service.get_target_profile_relationship_cache_summary(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
    )
    active_list_count = sum(
        1 for item in cache_summary.values() if bool(item.get("active_file_present"))
    )
    if active_list_count >= 2:
        fetch_status = "ready" if last_error is None else "partial"
    elif active_list_count == 1:
        fetch_status = "partial"
    else:
        fetch_status = "metadata_only"

    latest_relationship_fetch = None
    fetched_timestamps: list[str] = []
    for item in cache_summary.values():
        fetched_at = item.get("fetched_at")
        if isinstance(fetched_at, str):
            fetched_timestamps.append(fetched_at)
    if fetched_timestamps:
        latest_relationship_fetch = max(fetched_timestamps)

    db_service.upsert_target_profile(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
        username=metadata_username,
        full_name=metadata_full_name,
        follower_count=metadata_follower_count,
        following_count=metadata_following_count,
        is_private=bool(metadata.get("is_private", False)),
        is_verified=bool(metadata.get("is_verified", False)),
        me_following_account=bool(metadata.get("me_following_account", False)),
        being_followed_by_account=bool(
            metadata.get("being_followed_by_account", False)
        ),
        fetch_status=fetch_status,
        metadata_fetched_at=metadata_time,
        relationships_fetched_at=latest_relationship_fetch,
        last_error=last_error,
    )

    result = compute_followback_chances(
        pk_id=target_profile_id,
        reference_profile_id=reference_profile_id,
        app_user_id=app_user_id,
        metadata=metadata,
        include_overlap=fetch_relationships,
    )
    computed_at = datetime.now().isoformat()
    result["used_fresh_fetch"] = True
    result["graph_fetch_status"] = fetch_status
    result["relationship_cache"] = cache_summary
    result["target_profile"] = {
        "username": metadata_username,
        "full_name": metadata_full_name,
        "follower_count": metadata_follower_count,
        "following_count": metadata_following_count,
        **_metadata_feature_subset(metadata),
    }

    return (
        db_service.update_prediction(
            prediction_id,
            target_username=metadata_username,
            probability=result["followback_probability"],
            confidence=result["confidence"],
            status="completed",
            result_payload=result,
            feature_breakdown=result["feature_breakdown"],
            computed_at=computed_at,
            data_as_of=computed_at,
            outcome_status="confirmed"
            if metadata.get("being_followed_by_account")
            else "pending",
        )
        or {}
    )


def get_target_relationship_cache_status(
    app_user_id: str,
    instagram_user: dict,
    target_profile_id: str,
    sync_counts: bool = False,
) -> dict[str, dict[str, object]]:
    reference_profile_id = instagram_user["instagram_user_id"]
    if sync_counts:
        profile = _build_profile(instagram_user)
        previous_target_metadata = user_details_cache.load_target(
            app_user_id,
            reference_profile_id,
            target_profile_id,
        )
        metadata = instagram_gateway.get_target_user_data(
            app_user_id=app_user_id,
            instagram_user_id=reference_profile_id,
            profile=profile,
            target_user_id=target_profile_id,
            caller_service="account_handler",
            caller_method="get_target_relationship_cache_status",
            force_refresh=True,
        )
        _refresh_target_profile_image_cache_if_changed(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            previous_metadata=previous_target_metadata,
            current_metadata=metadata,
        )
        metadata_time = datetime.now().isoformat()
        metadata_follower_count = _as_int(metadata.get("account_followers_count"))
        metadata_following_count = _as_int(metadata.get("account_following_count"))
        cached_profile = db_service.get_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
        )
        db_service.upsert_target_profile(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            username=_as_str(metadata.get("username"))
            or (cached_profile or {}).get("username"),
            full_name=_as_str(metadata.get("full_name"))
            or (cached_profile or {}).get("full_name"),
            follower_count=metadata_follower_count,
            following_count=metadata_following_count,
            is_private=bool(metadata.get("is_private", False)),
            is_verified=bool(metadata.get("is_verified", False)),
            me_following_account=bool(metadata.get("me_following_account", False)),
            being_followed_by_account=bool(
                metadata.get("being_followed_by_account", False)
            ),
            fetch_status=(cached_profile or {}).get("fetch_status") or "metadata_only",
            metadata_fetched_at=metadata_time,
            relationships_fetched_at=(cached_profile or {}).get(
                "relationships_fetched_at"
            ),
            last_error=(cached_profile or {}).get("last_error"),
        )
        _invalidate_changed_count_caches(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            follower_count=metadata_follower_count,
            following_count=metadata_following_count,
            invalidated_at=metadata_time,
        )

    return db_service.get_target_profile_relationship_cache_summary(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        target_profile_id=target_profile_id,
    )


def record_prediction_feedback(
    prediction_id: str,
    assessment_status: str,
    notes: str | None = None,
    observed_at: str | None = None,
    source: str = "manual",
    expected_direction: str | None = None,
    expected_value: float | None = None,
) -> dict:
    prediction = db_service.get_prediction(prediction_id)
    if not prediction:
        raise ValueError("Prediction not found")

    evidence: dict = {"prediction_type": prediction.get("prediction_type")}
    actual_probability = prediction.get("probability")
    if actual_probability is not None:
        evidence["actual_probability"] = actual_probability
    if expected_direction is not None:
        evidence["expected_direction"] = expected_direction
    if expected_value is not None:
        evidence["expected_value"] = expected_value

    assessment = db_service.create_prediction_assessment(
        prediction_id=prediction_id,
        assessment_status=assessment_status,
        source=source,
        notes=notes,
        observed_at=observed_at,
        evidence=evidence,
    )
    db_service.update_prediction(
        prediction_id,
        outcome_status=assessment_status,
        status=prediction.get("status") or "completed",
    )
    return assessment


def reconcile_followback_predictions(
    app_user_id: str,
    reference_profile_id: str,
    follower_ids: set[str],
    observed_at: str | None = None,
) -> int:
    observed_at = observed_at or datetime.now().isoformat()
    updated = 0
    for prediction in db_service.list_active_followback_predictions(
        app_user_id, reference_profile_id
    ):
        prediction_id = prediction["prediction_id"]
        target_profile_id = prediction["target_profile_id"]
        assessments = db_service.list_prediction_assessments(prediction_id)
        if any(item["assessment_status"] == "correct" for item in assessments):
            continue

        if target_profile_id in follower_ids:
            db_service.create_prediction_assessment(
                prediction_id=prediction_id,
                assessment_status="correct",
                source="scan_reconciliation",
                notes="Target appeared in latest follower snapshot",
                observed_at=observed_at,
                evidence={"target_profile_id": target_profile_id},
            )
            db_service.update_prediction(
                prediction_id,
                outcome_status="correct",
                status="completed",
            )
            updated += 1
            continue

        expires_at = prediction.get("expires_at")
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) <= datetime.now():
                    db_service.create_prediction_assessment(
                        prediction_id=prediction_id,
                        assessment_status="wrong",
                        source="scan_reconciliation",
                        notes="Prediction expired without observed follow-back",
                        observed_at=observed_at,
                        evidence={"target_profile_id": target_profile_id},
                    )
                    db_service.update_prediction(
                        prediction_id,
                        outcome_status="wrong",
                        status="completed",
                    )
                    updated += 1
            except ValueError:
                continue
    return updated
