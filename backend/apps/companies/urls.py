from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.companies import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")

urlpatterns = [
    path("companies/", include(router.urls)),
]
