import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
import routes.ops as ops_routes
from services import ops_auth


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(ops_routes.router)
    return app


def _configured_client():
    return (
        TestClient(_app()),
        patch.object(settings, "ops_admin_username", "admin"),
        patch.object(settings, "ops_admin_password", "test-password"),
        patch.object(settings, "ops_session_hours", 12),
        patch.object(settings, "ops_cookie_secure", False),
    )


def test_ops_page_and_api_require_login_then_logout_revokes_session():
    client, username, password, hours, secure = _configured_client()
    ops_auth.reset_auth_state()
    with username, password, hours, secure, client:
        page = client.get("/ops", follow_redirects=False)
        assert page.status_code == 303
        assert page.headers["location"] == "/ops/login"

        analysis_page = client.get("/ops/account-ban-analysis", follow_redirects=False)
        assert analysis_page.status_code == 303
        assert analysis_page.headers["location"] == "/ops/login"

        flow_page = client.get("/ops/system-flow", follow_redirects=False)
        assert flow_page.status_code == 303
        assert flow_page.headers["location"] == "/ops/login"

        assert client.get("/ops/api/summary").status_code == 401
        assert client.get("/ops/api/system-flow").status_code == 401
        assert client.delete("/ops/api/sybil/1").status_code == 401

        wrong = client.post(
            "/ops/api/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert wrong.status_code == 401
        assert ops_auth.SESSION_COOKIE_NAME not in wrong.cookies

        logged_in = client.post(
            "/ops/api/login",
            json={"username": "admin", "password": "test-password"},
        )
        assert logged_in.status_code == 200
        cookie = logged_in.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Path=/ops" in cookie

        assert client.get("/ops").status_code == 200
        assert client.get("/ops/account-ban-analysis").status_code == 200
        assert client.get("/ops/system-flow").status_code == 200
        assert client.delete("/ops/api/sybil/1").status_code == 403

        logged_out = client.post(
            "/ops/api/logout",
            headers={"X-Ops-Request": "1"},
        )
        assert logged_out.status_code == 200
        assert client.get("/ops/api/summary").status_code == 401
    ops_auth.reset_auth_state()


def test_ops_login_is_rate_limited_after_five_failures():
    client, username, password, hours, secure = _configured_client()
    ops_auth.reset_auth_state()
    with username, password, hours, secure, client:
        for _ in range(5):
            response = client.post(
                "/ops/api/login",
                json={"username": "admin", "password": "wrong"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/ops/api/login",
            json={"username": "admin", "password": "test-password"},
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0
    ops_auth.reset_auth_state()


def test_ops_session_expires_and_can_be_revoked():
    with patch.object(settings, "ops_session_hours", 1):
        ops_auth.reset_auth_state()
        token = ops_auth.create_session(now=100)
        assert ops_auth.session_valid(token, now=100)
        assert not ops_auth.session_valid(token, now=3701)

        token = ops_auth.create_session(now=4000)
        ops_auth.revoke_session(token)
        assert not ops_auth.session_valid(token, now=4001)
    ops_auth.reset_auth_state()


def test_login_page_does_not_embed_credentials():
    source = Path("routes/static/ops_login.html").read_text()
    assert 'autocomplete="username"' in source
    assert 'autocomplete="current-password"' in source
    assert 'value="admin"' not in source
    assert "OPS_ADMIN_PASSWORD" not in source


def test_ops_ui_uses_session_logout_and_same_origin_write_header():
    source = Path("routes/static/ops.html").read_text()
    assert 'id="logout"' in source
    assert "/ops/api/logout" in source
    assert "'X-Ops-Request':'1'" in source
    assert "X-Ops-Write-Secret" not in source
    assert "window.prompt" not in source


def test_account_ban_analysis_page_contains_audited_views():
    source = Path("routes/static/account_ban_analysis.html").read_text()
    for expected in (
        "账号封禁邮件统一分析",
        'data-view="cases"',
        'data-view="conversations"',
        "导出当前表格 CSV",
        '["C01"',
        '["C30"',
        '["cnv_1jber66z"',
        '["cnv_1jb3qg63"',
        "仅草稿未发送",
        "模板后再次回复",
    ):
        assert expected in source
    assert source.count('["C') == 30
    assert source.count('["cnv_') == 35
    assert 'href="/ops/account-ban-analysis"' in Path("routes/static/ops.html").read_text()


def test_system_flow_page_animates_one_email_journey_with_live_telemetry():
    source = Path("routes/static/system_flow.html").read_text()
    for expected in (
        'id="neural"',
        "FRONT-AGENT / NEURAL FLOW",
        "ONE EMAIL · COMPLETE JOURNEY",
        "FLOW DEMO",
        "NODE_DEF",
        "EDGE_DEF",
        "SCENARIOS",
        "drawNeuralField",
        "drawEdge",
        "drawCore",
        "drawJourneyPath",
        "drawJourney",
        "drawMailToken",
        "requestAnimationFrame(frame)",
        "pointermove",
        "showPanel",
        "/ops/api/system-flow",
        "setInterval(load,8000)",
    ):
        assert expected in source
    assert 'class="stage"' not in source
    assert "createRadialGradient" in source
    assert "RECOVERY" in source
    assert "DRAFT" in source
    assert "LINEAR" in source
    assert 'data-scenario="reply"' in source
    assert 'data-scenario="ticket"' in source
    assert 'data-scenario="handoff"' in source
    assert 'data-scenario="retry"' in source
    assert 'href="/ops/system-flow"' in Path("routes/static/ops.html").read_text()


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()


if __name__ == "__main__":
    run_all()
