from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.companies import views

router = DefaultRouter()
# Categorias primeiro: o prefixo mais específico tem de ser registrado antes, senão
# `/companies/categories/` cairia no detalhe de empresa. A rota já existia neste caminho e
# não muda — o frontend continua funcionando.
router.register("companies/categories", views.CategoryViewSet, basename="category")
router.register("companies", views.CompanyViewSet, basename="company")

urlpatterns = [
    path("", include(router.urls)),
]
