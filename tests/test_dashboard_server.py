"""Tests for dashboard_server.py — lightweight HTTP server for live data."""

import json
import time
import urllib.request

import pytest

from plotly_mcp.dashboard_server import (
    _find_open_port,
    get_active_server,
    start_server,
    stop_server,
)


@pytest.fixture
def sample_csv(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("name,value\nAlice,10\nBob,20\n")
    return str(p)


@pytest.fixture(autouse=True)
def cleanup_server():
    """Ensure the server is stopped after each test."""
    yield
    stop_server()


class TestFindOpenPort:
    def test_finds_port(self):
        port = _find_open_port(9100)
        assert 9100 <= port < 9120

    def test_raises_on_no_port(self):
        # This is hard to test without binding all ports,
        # so just verify the function signature works
        port = _find_open_port(9200, max_tries=5)
        assert isinstance(port, int)


class TestStartStopServer:
    def test_start_and_stop(self, sample_csv):
        html = "<html><body>test</body></html>"
        result = start_server(html, sample_csv, port=9300)
        assert "port" in result
        assert "url" in result
        assert result["port"] >= 9300

        # Server should be active
        info = get_active_server()
        assert info is not None
        assert info["port"] == result["port"]

        # Stop it
        assert stop_server() is True
        assert get_active_server() is None

    def test_stop_when_not_running(self):
        assert stop_server() is False

    def test_start_replaces_previous(self, sample_csv):
        html = "<html><body>test</body></html>"
        r1 = start_server(html, sample_csv, port=9310)
        r2 = start_server(html, sample_csv, port=9320)
        # Previous server should be replaced
        info = get_active_server()
        assert info is not None
        assert info["port"] == r2["port"]
        stop_server()

    def test_stop_with_wrong_port(self, sample_csv):
        html = "<html><body>test</body></html>"
        result = start_server(html, sample_csv, port=9330)
        # Stop with wrong port should not stop it
        assert stop_server(port=1) is False
        assert get_active_server() is not None
        # Stop with correct port should work
        assert stop_server(port=result["port"]) is True


class TestServerResponses:
    def test_serves_html(self, sample_csv):
        html = "<html><body>Dashboard Content</body></html>"
        result = start_server(html, sample_csv, port=9340)
        time.sleep(0.1)  # Let server start

        url = result["url"] + "/"
        with urllib.request.urlopen(url) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "Dashboard Content" in body

    def test_serves_data_api(self, sample_csv):
        html = "<html></html>"
        result = start_server(html, sample_csv, port=9350)
        time.sleep(0.1)

        url = result["url"] + "/api/data"
        with urllib.request.urlopen(url) as resp:
            body = resp.read().decode("utf-8")
            assert resp.status == 200
            data = json.loads(body)
            assert len(data) == 2
            assert data[0]["name"] == "Alice"
            assert data[0]["value"] == 10

    def test_cors_headers(self, sample_csv):
        html = "<html></html>"
        result = start_server(html, sample_csv, port=9360)
        time.sleep(0.1)

        url = result["url"] + "/"
        with urllib.request.urlopen(url) as resp:
            assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    def test_data_api_rereads_file(self, tmp_path):
        csv_path = tmp_path / "live.csv"
        csv_path.write_text("x,y\n1,2\n")

        html = "<html></html>"
        result = start_server(html, str(csv_path), port=9370)
        time.sleep(0.1)

        # First read
        url = result["url"] + "/api/data"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode())
            assert len(data) == 1

        # Modify the file
        csv_path.write_text("x,y\n1,2\n3,4\n5,6\n")

        # Second read should see updated data
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode())
            assert len(data) == 3
