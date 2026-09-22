import os
from unittest.mock import Mock, patch

import pytest
import requests

from app import create_app, db


@pytest.fixture()
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": os.environ.get("TEST_DATABASE_URL", "sqlite://"),
        "USERS_API_URL": "https://users.example/users",
    })
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def payload():
    return dict(cliente_id=1, codigo_acao="PETR4", quantidade=3,
                preco_unitario="10.15", data_transacao="2026-09-22")


@pytest.fixture()
def users():
    with patch("app.requests.get") as get:
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"id": 1, "email": "cliente@example.com"}
        yield get


def test_create_filter_delete(client, payload, users):
    payload["valor_total"] = "0.01"
    payload["cliente_email"] = "falso@example.com"
    result = client.post("/transacao", json=payload)
    assert result.status_code == 201
    data = result.get_json()
    assert data["valor_total"] == "30.45"
    assert data["cliente_email"] == "cliente@example.com"
    users.assert_called_once_with("https://users.example/users/1", timeout=5)
    assert client.get("/transacao").get_json() == [data]
    assert client.get("/transacao?cliente_id=1").get_json() == [data]
    assert client.get("/transacao?cliente_id=2").get_json() == []
    assert client.delete(f"/transacao/{data['id']}").status_code == 204
    assert client.delete(f"/transacao/{data['id']}").status_code == 404
    assert client.get("/transacao").get_json() == []


def test_missing_user(client, payload, users):
    users.return_value.status_code = 404
    assert client.post("/transacao", json=payload).status_code == 404
    assert client.get("/transacao").get_json() == []


@pytest.mark.parametrize("error,status", [(requests.Timeout(), 504), (requests.ConnectionError(), 502)])
def test_service_failure(client, payload, users, error, status):
    users.side_effect = error
    assert client.post("/transacao", json=payload).status_code == status
    assert client.get("/transacao").get_json() == []


@pytest.mark.parametrize("user", [{}, [], {"email": ""}, {"email": None}])
def test_invalid_user_response(client, payload, users, user):
    users.return_value.json.return_value = user
    assert client.post("/transacao", json=payload).status_code == 502


@pytest.mark.parametrize("field,value", [
    ("cliente_id", True), ("cliente_id", 0), ("quantidade", -1),
    ("quantidade", 1.5), ("preco_unitario", "NaN"),
    ("preco_unitario", "Infinity"), ("preco_unitario", "0"),
    ("preco_unitario", "0.001"), ("preco_unitario", "9999999999999999"),
    ("codigo_acao", " "), ("data_transacao", "2026-02-30"),
    ("data_transacao", "20260922"),
])
def test_invalid_fields(client, payload, users, field, value):
    payload[field] = value
    assert client.post("/transacao", json=payload).status_code == 400
    users.assert_not_called()


@pytest.mark.parametrize("body", [{}, [], None])
def test_invalid_body(client, body):
    assert client.post("/transacao", json=body, content_type="application/json").status_code == 400


@pytest.mark.parametrize("value", ["abc", "0", "-1", "1.5", ""])
def test_invalid_filter(client, value):
    assert client.get(f"/transacao?cliente_id={value}").status_code == 400


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}
