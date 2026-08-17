from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.providers import views

router = DefaultRouter()
router.register("sources", views.CompanySourceViewSet, basename="company-source")

urlpatterns = [
    path("providers/", include(router.urls)),
]
