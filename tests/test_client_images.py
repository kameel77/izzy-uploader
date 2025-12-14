from pathlib import Path
from typing import Any, Dict

import pytest

from izzy_uploader.client import IzzyleaseClient
from izzy_uploader.config import ServiceConfig


class FakeTokenProvider:
    def get_token(self) -> str:
        return "test-token"


class DummyResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:  # pragma: no cover - trivial
        return self._body


@pytest.fixture()
def client_config(tmp_path: Path) -> ServiceConfig:
    return ServiceConfig(
        api_base_url="https://api.example.com",
        token_url="https://api.example.com/oauth/token",
        client_id="client",
        client_secret="secret",
        dealer_id=None,
        state_file=tmp_path / "state.json",
        timeout=1.0,
    )


def test_upload_car_image_builds_multipart(monkeypatch: pytest.MonkeyPatch, client_config: ServiceConfig) -> None:
    captured: Dict[str, Any] = {}

    def fake_urlopen(req, timeout=None, context=None):  # type: ignore[override]
        captured["request"] = req
        return DummyResponse(b'{"imageId":"abc-123"}')

    monkeypatch.setattr("izzy_uploader.client.request.urlopen", fake_urlopen)

    client = IzzyleaseClient(client_config, token_provider=FakeTokenProvider())
    image_id = client.upload_car_image(
        "car-1",
        b"image-bytes",
        content_type="image/png",
        filename="main.png",
    )

    assert image_id == "abc-123"
    req = captured["request"]
    assert req.get_method() == "POST"
    assert req.full_url == "https://api.example.com/external/cars/car-1/images"
    assert req.headers["Authorization"] == "Bearer test-token"
    assert req.headers["Accept"] == "application/json"
    content_type = req.headers["Content-type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    boundary = content_type.split("boundary=")[-1]
    body = req.data
    assert f'Content-Disposition: form-data; name="image"; filename="main.png"'.encode() in body
    assert f"--{boundary}--".encode() in body
    assert b"image-bytes" in body


def test_delete_car_image_uses_delete_method(monkeypatch: pytest.MonkeyPatch, client_config: ServiceConfig) -> None:
    captured: Dict[str, Any] = {}

    def fake_urlopen(req, timeout=None, context=None):  # type: ignore[override]
        captured["request"] = req
        return DummyResponse(b"{}")

    monkeypatch.setattr("izzy_uploader.client.request.urlopen", fake_urlopen)

    client = IzzyleaseClient(client_config, token_provider=FakeTokenProvider())
    client.delete_car_image("car-1", "img-2")

    req = captured["request"]
    assert req.get_method() == "DELETE"
    assert req.full_url == "https://api.example.com/external/cars/car-1/images/img-2"
    assert req.headers["Authorization"] == "Bearer test-token"
    assert req.headers["Accept"] == "application/json"
