from __future__ import annotations


def test_frontend_console_is_served(api_client) -> None:
    response = api_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "CloudDesk 运营工作台" in response.text
    assert "/app.js" in response.text
    assert "/styles.css" in response.text


def test_frontend_assets_reference_sse_endpoint(api_client) -> None:
    response = api_client.get("/app.js")

    assert response.status_code == 200
    assert "customer-consultations/stream" in response.text
    assert "knowledge/search" in response.text
    assert "auth/tokens" in response.text
    assert 'fetchRuntime("/traces")' in response.text
    assert 'fetchRuntime("/costs")' in response.text
    assert 'fetchRuntime("/agents")' in response.text


def test_frontend_styles_are_served(api_client) -> None:
    response = api_client.get("/styles.css")

    assert response.status_code == 200
    assert "event-log" in response.text
