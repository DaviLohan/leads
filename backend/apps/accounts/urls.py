from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts import views

router = DefaultRouter()
router.register("members", views.MemberViewSet, basename="member")
router.register("invitations", views.InvitationViewSet, basename="invitation")

auth_patterns = [
    path("csrf/", views.CsrfView.as_view(), name="csrf"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("organization/", views.SwitchOrganizationView.as_view(), name="switch-organization"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password-change"),
    path("password/reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("invitations/accept/", views.InvitationAcceptView.as_view(), name="invitation-accept"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("organizations/", include(router.urls)),
]
