import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.model import ModelService  # noqa: E402
from app.ratelimit import SlidingWindowLimiter  # noqa: E402
from app.security import client_id, valid_key  # noqa: E402
from ml.train import train  # noqa: E402

KEY = "chave-de-teste-123"
H = {"X-API-Key": KEY}


@pytest.fixture(scope="session")
def model_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("art") / "model.joblib"
    train(path, n_train=1500, n_test=300)
    return path


@pytest.fixture(scope="session")
def model(model_path):
    return ModelService(model_path)


def make_client(model, **kw):
    s = Settings(api_keys=(KEY, "outra-chave"), rate_limit_per_min=kw.pop("rate", 1000), **kw)
    return TestClient(create_app(s, model))


@pytest.fixture()
def client(model):
    with make_client(model) as c:
        yield c


# ---------------------------------------------------------------- operação
def test_health_and_ready_need_no_auth(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["model_version"]


def test_openapi_and_swagger_available(client):
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "Review Insight API"
    assert {"/v1/analyze", "/v1/analyze/batch", "/v1/model", "/health", "/ready", "/metrics"} <= set(spec["paths"])
    assert "APIKeyHeader" in spec["components"]["securitySchemes"]
    assert client.get("/docs").status_code == 200


# ---------------------------------------------------------------- autenticação
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "errada"}, {"X-API-Key": ""}])
def test_auth_required(client, headers):
    r = client.post("/v1/analyze", json={"text": "bom produto"}, headers=headers)
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"
    assert r.headers["WWW-Authenticate"] == "ApiKey"


def test_service_without_keys_returns_503(model):
    c = TestClient(create_app(Settings(api_keys=()), model))
    assert c.post("/v1/analyze", json={"text": "bom produto"}, headers=H).status_code == 503


def test_valid_key_constant_time_helper():
    assert valid_key("a", ("b", "a")) and not valid_key("c", ("a", "b")) and not valid_key("", ("a",))
    assert client_id("x") == client_id("x") != client_id("y") and "x" not in client_id("x")


# ---------------------------------------------------------------- inferência
def test_analyze_ok_and_schema(client):
    r = client.post("/v1/analyze", json={"text": "O pedido chegou com 10 dias de atraso e o suporte nunca respondeu"}, headers=H)
    assert r.status_code == 200
    body = r.json()
    res = body["result"]
    assert res["sentiment"] == "negativo" and res["negative_risk"] > 0.5
    assert res["topic"] in {"entrega", "produto", "atendimento", "preco"}
    assert abs(sum(res["sentiment_probabilities"].values()) - 1) < 0.01
    assert body["model_version"] and body["request_id"] == r.headers["X-Request-ID"]


def test_positive_review(client):
    r = client.post("/v1/analyze", json={"text": "Entrega super rápida e produto excelente, recomendo!"}, headers=H)
    assert r.json()["result"]["sentiment"] == "positivo"


def test_request_id_is_propagated(client):
    r = client.post("/v1/analyze", json={"text": "texto qualquer aqui"}, headers={**H, "X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123" and r.json()["request_id"] == "abc-123"


@pytest.mark.parametrize("payload", [{}, {"text": ""}, {"text": "  "}, {"text": 123}, {"texto": "x"}, []])
def test_validation_errors(client, payload):
    r = client.post("/v1/analyze", json=payload, headers=H)
    assert r.status_code == 422 and r.json()["error"] == "validation_error"


def test_text_too_long(model):
    c = make_client(model, max_text_chars=50)
    r = c.post("/v1/analyze", json={"text": "a" * 51}, headers=H)
    assert r.status_code == 422 and "excede" in r.json()["detail"]


def test_batch_ok_matches_single(client):
    items = [{"id": "a", "text": "Chegou rápido e bem embalado, adorei!"},
             {"id": "b", "text": "Paguei caro e o produto veio quebrado."}]
    r = client.post("/v1/analyze/batch", json={"items": items}, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2 and [x["id"] for x in data["results"]] == ["a", "b"]
    single = client.post("/v1/analyze", json={"text": items[1]["text"]}, headers=H).json()["result"]
    assert data["results"][1]["sentiment"] == single["sentiment"]
    assert data["results"][1]["negative_risk"] == pytest.approx(single["negative_risk"])


def test_batch_limits(model):
    c = make_client(model, max_batch_size=3)
    ok = [{"id": str(i), "text": "produto bom demais"} for i in range(3)]
    assert c.post("/v1/analyze/batch", json={"items": ok}, headers=H).status_code == 200
    r = c.post("/v1/analyze/batch", json={"items": ok + [{"id": "9", "text": "mais um item"}]}, headers=H)
    assert r.status_code == 422 and "máximo" in r.json()["detail"]
    assert c.post("/v1/analyze/batch", json={"items": []}, headers=H).status_code == 422


def test_needs_human_review_flag(model):
    strict = TestClient(create_app(Settings(api_keys=(KEY,), review_threshold=0.999), model))
    r = strict.post("/v1/analyze", json={"text": "recebi o pedido ontem"}, headers=H)
    assert r.json()["result"]["needs_human_review"] is True


def test_model_info_has_honest_metrics(client):
    r = client.get("/v1/model", headers=H)
    assert r.status_code == 200
    body = r.json()
    assert "handwritten" in body["metrics"]["sentiment"] and "sintéticos" in body["disclaimer"]
    assert client.get("/v1/model").status_code == 401


# ---------------------------------------------------------------- rate limit
def test_rate_limit_enforced_per_key(model):
    c = make_client(model, rate=3)
    for _ in range(3):
        assert c.post("/v1/analyze", json={"text": "texto de teste"}, headers=H).status_code == 200
    r = c.post("/v1/analyze", json={"text": "texto de teste"}, headers=H)
    assert r.status_code == 429 and r.json()["error"] == "rate_limited" and int(r.headers["Retry-After"]) >= 1
    # outra chave tem sua própria cota
    assert c.post("/v1/analyze", json={"text": "texto de teste"}, headers={"X-API-Key": "outra-chave"}).status_code == 200


def test_rate_limit_headers(client):
    r = client.post("/v1/analyze", json={"text": "texto de teste"}, headers=H)
    assert r.headers["X-RateLimit-Limit"] == "1000" and int(r.headers["X-RateLimit-Remaining"]) < 1000


def test_sliding_window_expires():
    lim = SlidingWindowLimiter(2, window_s=10)
    assert lim.check("c", now=0)[0] and lim.check("c", now=1)[0]
    allowed, remaining, retry = lim.check("c", now=2)
    assert not allowed and remaining == 0 and retry == pytest.approx(8)
    assert lim.check("c", now=10.5)[0]  # a primeira tentativa saiu da janela


# ---------------------------------------------------------------- métricas
def test_metrics_endpoint(client):
    client.post("/v1/analyze", json={"text": "produto ótimo e entrega rápida"}, headers=H)
    client.post("/v1/analyze", json={"text": "x"}, headers=H)  # 422
    client.get("/rota-inexistente")
    text = client.get("/metrics").text
    assert re.search(r'http_requests_total\{method="POST",path="/v1/analyze",status="200"\} 1', text)
    assert 'status="422"' in text and 'path="unmatched"' in text
    assert "http_request_duration_seconds_bucket" in text and "model_info{version=" in text
    assert re.search(r'predictions_total\{sentiment="\w+"\} \d+', text)


def test_unhandled_error_is_hidden(model):
    app = create_app(Settings(api_keys=(KEY,)), model)

    @app.get("/boom")
    def boom():
        raise RuntimeError("segredo interno")

    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500 and "segredo" not in r.text and r.json()["error"] == "internal_error"


# ---------------------------------------------------------------- modelo
def test_model_is_deterministic_and_batch_consistent(model):
    texts = ["entrega atrasada demais", "preço justo e produto bom", "falei com o suporte pelo chat"]
    a, b = model.predict(texts), model.predict(texts)
    assert a == b
    assert [model.predict([t])[0]["sentiment"] for t in texts] == [x["sentiment"] for x in a]
