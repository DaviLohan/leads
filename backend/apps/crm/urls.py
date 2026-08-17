from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.crm import views

router = DefaultRouter()
router.register("pipelines", views.PipelineViewSet, basename="pipeline")
router.register("leads", views.LeadViewSet, basename="lead")
router.register("lists", views.CompanyListViewSet, basename="company-list")
router.register("suppressions", views.SuppressionEntryViewSet, basename="suppression")

urlpatterns = [
    path("crm/", include(router.urls)),
]
