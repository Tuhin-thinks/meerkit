from typing import cast

from flask import Blueprint, jsonify, request, send_file

from meerkit.config import IMAGE_CACHE_DIR, profile_data_dir
from meerkit.routes import get_active_context
from meerkit.services import image_cache, persistence
from meerkit.services.downloader import enqueue_image_download

bp = Blueprint("images", __name__, url_prefix="/api")


@bp.get("/image/<pk_id>")
def get_image(pk_id: str):
    # Validate pk_id is numeric to prevent path traversal and SSRF via crafted IDs
    if not pk_id.isdigit():
        return jsonify({"error": "Invalid pk_id"}), 400

    instagram_user_id = request.args.get("profile_id") or request.args.get(
        "instagram_user_id"
    )
    app_user_id, context = get_active_context(instagram_user_id)
    if not app_user_id:
        body, status = context
        return jsonify(body), status

    instagram_user = cast(dict, context)
    data_dir = profile_data_dir(app_user_id, instagram_user["instagram_user_id"])

    # Serve from disk cache if available
    cached = image_cache.get_cached_image_path(pk_id)
    if cached:
        resp = send_file(cached, mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
        return resp

    url = persistence.get_profile_pic_url(
        app_user_id=app_user_id,
        reference_profile_id=instagram_user["user_id"],
        pk_id=pk_id,
        data_dir=data_dir,
    )
    if not url:
        return jsonify({"error": "User not found in latest scan"}), 404

    enqueue_image_download(app_user_id, instagram_user["instagram_user_id"], pk_id, url)
    resp = send_file(IMAGE_CACHE_DIR / "no-img-available.jpeg", mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp
