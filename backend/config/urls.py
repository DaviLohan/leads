"""URLs raiz.

A API é versionada sob `/api/v1/` desde o começo — versionar depois quebra cliente.
Health checks ficam fora do prefixo: sondas de infraestrutura não devem depender da
versão da API.
"""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core import health

api_v1: list[URLPattern | URLResolver] = [
    path("health/", health.live, name="api-health"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # O include abaixo usa o namespace "v1", então a rota do schema é "v1:schema".
    path("docs/", SpectacularSwaggerView.as_view(url_name="v1:schema"), name="docs"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.geography.urls")),
    path("", include("apps.discovery.urls")),
    path("", include("apps.analysis.urls")),
    # Os demais módulos de domínio entram aqui a partir da Etapa 10.
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
    path("api/v1/", include((api_v1, "v1"))),
]
