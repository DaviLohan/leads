from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.discovery import views

router = DefaultRouter()
router.register("searches", views.SearchViewSet, basename="search")
router.register("jobs", views.SearchJobViewSet, basename="search-job")

urlpatterns = [
    path("discovery/", include(router.urls)),
]
