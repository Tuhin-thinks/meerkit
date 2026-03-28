from pathlib import Path

import get_current_followers as gcf


def run_scoped_scan(
    app_user_id: str,
    data_dir: Path,
    csrf_token: str,
    session_id: str,
    target_user_id: str,
) -> dict:
    """Run one scoped scan directly in-process using explicit credentials."""
    return gcf.run_scan_for_api(
        app_user_id=app_user_id,
        data_dir=data_dir,
        csrf_token=csrf_token,
        session_id=session_id,
        reference_profile_id=target_user_id,
    )


def main() -> int:
    """CLI entrypoint is intentionally disabled; scans are called directly by scan_runner."""
    raise RuntimeError("Use run_scoped_scan() from meerkit.services.scan_runner")


if __name__ == "__main__":
    raise SystemExit(main())
