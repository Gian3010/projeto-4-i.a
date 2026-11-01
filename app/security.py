"""Autenticação por API key (header ``X-API-Key``) com comparação em tempo constante."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False,
                              description="Chave de API fornecida pelo administrador do serviço.")


def client_id(api_key: str) -> str:
    """Identificador estável e não reversível do cliente (nunca logamos a chave)."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:10]


def valid_key(candidate: str, keys: tuple[str, ...]) -> bool:
    ok = False
    for k in keys:  # percorre todas para não vazar qual chave casou pelo tempo
        ok |= hmac.compare_digest(candidate.encode(), k.encode())
    return ok


async def require_api_key(request: Request, key: str | None = Security(api_key_header)) -> str:
    settings = request.app.state.settings
    if not settings.api_keys:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Serviço sem API_KEYS configuradas.")
    if not key or not valid_key(key, settings.api_keys):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key ausente ou inválida.",
                            headers={"WWW-Authenticate": "ApiKey"})
    cid = client_id(key)
    request.state.client_id = cid
    return cid
