import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import create_app


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>VideoForge</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    return dist


def test_production_app_serves_spa_routes_and_static_assets(tmp_path):
    client = TestClient(create_app(serve_frontend=True, frontend_dist=_dist(tmp_path)))

    assert client.get("/").status_code == 200
    assert client.get("/library").text == "<html>VideoForge</html>"
    assert client.get("/editor/project_123").text == "<html>VideoForge</html>"
    assert client.get("/assets/app.js").text == "console.log('ok')"
    assert client.get("/assets/missing.js").status_code == 404


def test_api_routes_are_not_captured_by_spa_fallback(tmp_path):
    client = TestClient(create_app(serve_frontend=True, frontend_dist=_dist(tmp_path)))

    assert client.get("/api/health").json()["status"] == "ok"
    missing = client.get("/api/does-not-exist")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")


def test_spa_fallback_rejects_paths_outside_dist(tmp_path):
    client = TestClient(create_app(serve_frontend=True, frontend_dist=_dist(tmp_path)))

    response = client.get("/..%2F..%2Foutside.txt")
    assert response.status_code == 404


def test_production_mode_requires_index_html(tmp_path):
    with pytest.raises(RuntimeError, match="Frontend production build not found"):
        create_app(serve_frontend=True, frontend_dist=tmp_path / "missing-dist")
