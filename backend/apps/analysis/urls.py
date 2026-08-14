from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.analysis import views

router = DefaultRouter()
router.register("scans", views.WebsiteScanViewSet, basename="website-scan")
router.register("opportunities", views.OpportunityViewSet, basename="opportunity")

urlpatterns = [
    path("analysis/", include(router.urls)),
]
