"""Middlewares de infraestrutura: correlação de requisição e headers de segurança."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.core.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 64


class RequestIDMiddleware:
    """Propaga um identificador por requisição, do header ao log e à resposta.

    O valor recebido do cliente é truncado — ele entra em logs, então não pode ser
    usado para inflar linha de log nem injetar conteúdo.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = self._sanitize(incoming) or uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[REQUEST_ID_HEADER] = request_id
        return response

    @staticmethod
    def _sanitize(value: str) -> str:
        cleaned = "".join(c for c in value if c.isalnum() or c in "-_")
        return cleaned[:_MAX_REQUEST_ID_LENGTH]


class SecurityHeadersMiddleware:
    """Adiciona a CSP. Os demais headers vêm do SecurityMiddleware do Django."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.policy = getattr(settings, "CONTENT_SECURITY_POLICY", "")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if self.policy and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = self.policy
        return response
