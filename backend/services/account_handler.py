import math
from datetime import datetime, timedelta

import insta_interface as ii
from backend.services import db_service

_PREDICTION_TTL = timedelta(days=7)
_CACHE_FRESHNESS = timedelta(hours=6)
_HISTORICAL_REFERENCE_LIMIT = 400


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


def _build_profile(credentials: dict) -> ii.InstagramProfile:
    return ii.InstagramProfile(
        csrf_token=credentials["csrf_token"],
        session_id=credentials["session_id"],
        user_id=credentials["user_id"],
    )


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

    return {
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


def compute_followback_chances(
    pk_id: str,
    reference_profile_id: str,
    app_user_id: str | None = None,
    metadata: dict[str, object] | None = None,
):
    """Compute follow-back probability for one target user using cached profile data."""
    if not app_user_id:
        raise ValueError("app_user_id is required to compute followback chances")

    target_profile = db_service.get_target_profile(
        app_user_id, reference_profile_id, pk_id
    )
    latest_follower_ids = db_service.get_latest_scanned_profile_ids(
        app_user_id, reference_profile_id
    )
    target_followers = db_service.get_target_profile_relationship_ids(
        app_user_id, reference_profile_id, pk_id, "followers"
    )
    target_following = db_service.get_target_profile_relationship_ids(
        app_user_id, reference_profile_id, pk_id, "following"
    )

    score = _logit(0.28)
    confidence = 0.24
    reasons: list[str] = []
    metadata_features = _metadata_feature_subset(metadata)

    overlap_followers = len(target_followers & latest_follower_ids)
    overlap_following = len(target_following & latest_follower_ids)
    feature_breakdown = _build_feature_breakdown(
        target_profile=target_profile,
        metadata_features=metadata_features,
        latest_follower_ids=latest_follower_ids,
        target_followers=target_followers,
        target_following=target_following,
        overlap_followers=overlap_followers,
        overlap_following=overlap_following,
    )

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
        if isinstance(follower_count, int):
            if follower_count <= 2_000:
                score += 0.18
                reasons.append("Smaller audience size increases follow-back odds")
            elif follower_count >= 100_000:
                score -= 0.42
                reasons.append("Large audience size lowers follow-back odds")

        following_count = _as_int(target_profile.get("following_count"))
        following_to_follower_ratio = _safe_ratio(following_count, follower_count)
        if following_to_follower_ratio >= 0.8:
            score += 0.16
            reasons.append("Higher follow ratio can indicate stronger reciprocity")
        elif follower_count and following_to_follower_ratio <= 0.08:
            score -= 0.12
            reasons.append("Low follow ratio can reduce reciprocity odds")

    mutual_followers_count = _as_int(metadata_features.get("mutual_followers_count"))
    if isinstance(mutual_followers_count, int) and mutual_followers_count > 0:
        score += min(0.55, mutual_followers_count * 0.06)
        confidence += min(0.14, 0.03 + mutual_followers_count * 0.015)
        reasons.append("Mutual followers increase likelihood of follow-back")

    mutual_to_follower_ratio = _safe_ratio(
        mutual_followers_count,
        _as_int(target_profile.get("follower_count")) if target_profile else None,
    )
    if mutual_to_follower_ratio >= 0.03:
        score += min(0.35, mutual_to_follower_ratio * 3.0)
        reasons.append("Mutual follower ratio suggests a closer audience overlap")

    media_count = _as_int(metadata_features.get("media_count"))
    if isinstance(media_count, int) and media_count >= 1000:
        score -= 0.16
        reasons.append("Very high media volume slightly lowers follow-back odds")

    category = (_as_str(metadata_features.get("category")) or "").lower()
    if category and any(
        token in category
        for token in ("artist", "public figure", "creator", "celebrity", "musician")
    ):
        score -= 0.18
        reasons.append("Public-figure style categories reduce follow-back odds")

    if metadata_features.get("is_professional_account"):
        score -= 0.14
        reasons.append("Professional accounts are slightly less likely to follow back")

    biography = _as_str(metadata_features.get("biography")) or ""
    if biography and len(biography) >= 80:
        confidence += 0.03

    if metadata_features.get("has_highlight_reels"):
        confidence += 0.02

    if overlap_followers:
        score += min(0.5, overlap_followers * 0.05)
        confidence += 0.1
        reasons.append("Target followers overlap with the active audience")
    if overlap_following:
        score += min(0.42, overlap_following * 0.04)
        confidence += 0.08
        reasons.append("Target following overlaps with the active audience")

    overlap_followers_ratio = _safe_ratio(overlap_followers, len(latest_follower_ids))
    if overlap_followers_ratio >= 0.01:
        score += min(0.35, overlap_followers_ratio * 5.0)

    overlap_following_ratio = _safe_ratio(overlap_following, len(latest_follower_ids))
    if overlap_following_ratio >= 0.01:
        score += min(0.28, overlap_following_ratio * 4.0)

    if target_followers or target_following:
        confidence += 0.16

    graph_fetch_status = feature_breakdown["graph_fetch_status"]
    probability = _sigmoid(score)
    historical_reference = _compute_historical_reference(
        app_user_id=app_user_id,
        reference_profile_id=reference_profile_id,
        feature_breakdown=feature_breakdown,
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

    return {
        "target_profile_id": pk_id,
        "target_username": target_profile.get("username") if target_profile else None,
        "followback_probability": probability,
        "confidence": confidence,
        "matched_followers_count": overlap_followers,
        "matched_following_count": overlap_following,
        "graph_fetch_status": graph_fetch_status,
        "used_cached_followers": bool(target_followers),
        "used_cached_following": bool(target_following),
        "used_fresh_fetch": False,
        "statistical_reference_count": historical_reference["sample_count"],
        "statistical_reference_rate": historical_reference["calibrated_probability"],
        "global_historical_rate": historical_reference["global_rate"],
        "feature_breakdown": feature_breakdown,
        "reasons": reasons,
    }


def request_followback_prediction(
    app_user_id: str,
    instagram_user: dict,
    username: str | None = None,
    user_id: str | None = None,
    refresh: bool = False,
    force_background: bool = False,
) -> dict:
    if not username and not user_id:
        raise ValueError("username or user_id is required")

    profile = _build_profile(instagram_user)
    target_profile_id = user_id or ii.resolve_target_user_pk(username or "", profile)
    if not target_profile_id:
        raise ValueError("Could not resolve target instagram user")

    cached_profile = db_service.get_target_profile(
        app_user_id, instagram_user["instagram_user_id"], target_profile_id
    )
    target_username = username or (cached_profile or {}).get("username")
    current_time = datetime.now().isoformat()
    expires_at = (datetime.now() + _PREDICTION_TTL).isoformat()

    if (
        not refresh
        and not force_background
        and _cache_ready(
            app_user_id, instagram_user["instagram_user_id"], target_profile_id
        )
    ):
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
        )
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


def refresh_followback_prediction(prediction_id: str, instagram_user: dict) -> dict:
    prediction = db_service.get_prediction(prediction_id)
    if not prediction:
        raise ValueError("Prediction not found")

    profile = _build_profile(instagram_user)
    target_profile_id = prediction["target_profile_id"]
    reference_profile_id = prediction["reference_profile_id"]
    app_user_id = prediction["app_user_id"]

    metadata = ii.get_target_user_data(profile, target_profile_id)
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
    fetch_status = "ready"
    last_error: str | None = None
    followers: list[ii.FollowerUserRecord] = []
    following: list[ii.FollowerUserRecord] = []
    try:
        followers = ii.get_target_followers_v2(profile, target_profile_id)
        db_service.replace_target_profile_relationships(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            relationship_type="followers",
            profiles=followers,
            fetched_at=relationships_time,
        )
    except Exception as exc:
        fetch_status = "partial"
        last_error = str(exc)

    try:
        following = ii.get_target_following_v2(profile, target_profile_id)
        db_service.replace_target_profile_relationships(
            app_user_id=app_user_id,
            reference_profile_id=reference_profile_id,
            target_profile_id=target_profile_id,
            relationship_type="following",
            profiles=following,
            fetched_at=relationships_time,
        )
    except Exception as exc:
        fetch_status = "partial" if fetch_status == "ready" else fetch_status
        last_error = str(exc)

    if not followers and not following:
        fetch_status = "metadata_only"

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
        relationships_fetched_at=relationships_time,
        last_error=last_error,
    )

    result = compute_followback_chances(
        pk_id=target_profile_id,
        reference_profile_id=reference_profile_id,
        app_user_id=app_user_id,
        metadata=metadata,
    )
    computed_at = datetime.now().isoformat()
    result["used_fresh_fetch"] = True
    result["graph_fetch_status"] = fetch_status
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


def record_prediction_feedback(
    prediction_id: str,
    assessment_status: str,
    notes: str | None = None,
    observed_at: str | None = None,
    source: str = "manual",
) -> dict:
    prediction = db_service.get_prediction(prediction_id)
    if not prediction:
        raise ValueError("Prediction not found")

    assessment = db_service.create_prediction_assessment(
        prediction_id=prediction_id,
        assessment_status=assessment_status,
        source=source,
        notes=notes,
        observed_at=observed_at,
        evidence={"prediction_type": prediction.get("prediction_type")},
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
