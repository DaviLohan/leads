from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.geography import views

router = DefaultRouter()
router.register("states", views.StateViewSet, basename="state")
router.register("cities", views.CityViewSet, basename="city")

urlpatterns = [
    path("geography/", include(router.urls)),
]
