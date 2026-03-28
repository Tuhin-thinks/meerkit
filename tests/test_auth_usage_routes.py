from meerkit.app import create_app


def test_instagram_api_usage_summary_requires_login():
    app = create_app()
    client = app.test_client()

    response = client.get('/api/auth/instagram-api-usage')

    assert response.status_code == 401
    payload = response.get_json()
    assert payload['error'] == 'Not logged in'


def test_instagram_api_usage_summary_returns_grouped_payload(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        'meerkit.routes.auth._current_app_user',
        lambda: ('app_test_user', 'Test User'),
    )
    monkeypatch.setattr(
        'meerkit.routes.auth.db_service.get_instagram_api_usage_summary',
        lambda **kwargs: {
            'generated_at': '2026-03-22T10:00:00',
            'window_start_24h': '2026-03-21T10:00:00',
            'totals': {'all_time_count': 9, 'last_24h_count': 3},
            'accounts': [
                {
                    'instagram_user_id': 'ig_123',
                    'all_time_count': 9,
                    'last_24h_count': 3,
                    'categories': [
                        {
                            'category': 'followers_discovery',
                            'all_time_count': 5,
                            'last_24h_count': 2,
                            'callers': [
                                {
                                    'caller_service': 'scan_flow',
                                    'caller_method': 'run_scan_for_api',
                                    'all_time_count': 5,
                                    'last_24h_count': 2,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(
        'meerkit.routes.auth.auth_service.get_instagram_users',
        lambda app_user_id: [
            {'instagram_user_id': 'ig_123', 'name': 'Primary Account'}
        ],
    )

    response = client.get('/api/auth/instagram-api-usage')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['totals']['all_time_count'] == 9
    assert payload['accounts'][0]['instagram_user_id'] == 'ig_123'
    assert payload['accounts'][0]['account_name'] == 'Primary Account'
    assert payload['accounts'][0]['categories'][0]['category'] == 'followers_discovery'
