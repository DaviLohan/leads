"""API de autenticação, organização ativa e gestão de membros.

Camada HTTP fina (CLAUDE.md): autentica, valida, delega para `services` e serializa.
Autenticação por sessão em cookie HTTPOnly + CSRF (ADR-0005) — nada de token no cliente.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import serializers as sz
from apps.accounts import services
from apps.accounts.middleware import (
    active_memberships,
    resolve_membership,
    set_active_organization,
)
from apps.accounts.models import Invitation, Membership, Organization, Role, User
from apps.accounts.permissions import MinRole
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.viewsets import TenantViewSet

logger = logging.getLogger(__name__)

# Mensagem única para credencial inválida: distinguir "e-mail não existe" de "senha errada"
# entrega a lista de usuários para quem quiser enumerá-la.
INVALID_CREDENTIALS = _("E-mail ou senha inválidos.")


def me_payload(request) -> dict:
    memberships = list(active_memberships(request.user))
    membership = getattr(request, "membership", None)
    return sz.MeSerializer(
        {
            "user": request.user,
            "organization": getattr(request, "organization", None),
            "role": membership.role if membership else None,
            "memberships": memberships,
        }
    ).data


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Entrega o cookie `csrftoken` ao SPA antes do primeiro POST."""

    permission_classes = [AllowAny]

    @extend_schema(responses={200: sz.DetailSerializer})
    def get(self, request):
        return Response({"detail": "ok"})


@extend_schema(request=sz.LoginSerializer, responses={200: sz.MeSerializer})
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = sz.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"].lower(),
            password=serializer.validated_data["password"],
        )
        # `authenticate` já devolve None para usuário inativo (ModelBackend), então a
        # mensagem é a mesma nos três casos: e-mail inexistente, senha errada e conta inativa.
        if user is None:
            return Response({"detail": INVALID_CREDENTIALS}, status=status.HTTP_401_UNAUTHORIZED)

        login(request, user)  # rotaciona a chave de sessão
        # O middleware já rodou, quando o usuário ainda era anônimo — sem isto a resposta do
        # login sairia sem organização e a tela mostraria "nenhuma organização ativa".
        membership = resolve_membership(request)
        request.membership = membership
        request.organization = membership.organization if membership else None

        record_audit(
            action=AuditLog.Action.LOGIN,
            object_type="User",
            object_id=user.pk,
            actor=user,
            request=request,
        )
        return Response(me_payload(request))


@extend_schema(request=None, responses={204: None})
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)  # apaga a sessão no servidor
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(responses={200: sz.MeSerializer})
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(me_payload(request))


@extend_schema(request=sz.SwitchOrganizationSerializer, responses={200: sz.MeSerializer})
class SwitchOrganizationView(APIView):
    """Troca a organização ativa da sessão."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = sz.SwitchOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        membership = (
            active_memberships(request.user)
            .filter(organization_id=serializer.validated_data["organization_id"])
            .first()
        )
        if membership is None:
            # 404: confirmar que a organização existe já seria informação demais.
            return Response(
                {"detail": _("Organização não encontrada.")}, status=status.HTTP_404_NOT_FOUND
            )

        set_active_organization(request, membership.organization)
        request.membership = membership
        request.organization = membership.organization
        return Response(me_payload(request))


@extend_schema(request=sz.PasswordChangeSerializer, responses={204: None})
class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = sz.PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": [_("Senha atual incorreta.")]})

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        # Mantém a sessão atual; as demais morrem porque o hash da senha mudou.
        update_session_auth_hash(request, request.user)

        record_audit(
            action=AuditLog.Action.UPDATE,
            object_type="User",
            object_id=request.user.pk,
            actor=request.user,
            changes={"password": "changed"},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(request=sz.PasswordResetRequestSerializer, responses={204: None})
class PasswordResetRequestView(APIView):
    """Solicita a redefinição de senha.

    Responde 204 sempre — inclusive para e-mail inexistente. Qualquer diferença de resposta
    ou de tempo vira um oráculo de quais e-mails têm conta.
    """

    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = sz.PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(
            email=serializer.validated_data["email"].lower(), is_active=True
        ).first()
        if user is not None:
            self._send_reset_email(user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _send_reset_email(user: User) -> None:
        """Envia o link por e-mail — nunca por log.

        Token de redefinição é credencial: registrá-lo daria acesso à conta a quem tivesse
        acesso aos logs. Em desenvolvimento o backend de e-mail é o console.
        """
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.FRONTEND_URL}/redefinir-senha?uid={uid}&token={token}"
        send_mail(
            subject=_("Redefinição de senha"),
            message=_("Para definir uma nova senha, acesse: %(link)s") % {"link": link},
            from_email=None,  # usa DEFAULT_FROM_EMAIL
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("password reset solicitado", extra={"user_id": str(user.pk)})


@extend_schema(request=sz.PasswordResetConfirmSerializer, responses={204: None})
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = sz.PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self._user_from_uid(serializer.validated_data["uid"])
        token = serializer.validated_data["token"]
        if user is None or not default_token_generator.check_token(user, token):
            raise ValidationError({"token": [_("Link inválido ou expirado.")]})

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        # Trocar a senha muda o hash da sessão: o token vira inútil e as sessões antigas caem.
        record_audit(
            action=AuditLog.Action.UPDATE,
            object_type="User",
            object_id=user.pk,
            actor=user,
            changes={"password": "reset"},
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @staticmethod
    def _user_from_uid(uid: str) -> User | None:
        """Usuário correspondente ao `uid` do link, ou `None`.

        O UUID é validado antes da consulta: `filter(pk="abc")` levanta o
        `ValidationError` do Django, que não herda de `ValueError` e escaparia daqui
        como 500 num endpoint público. `uuid.UUID()` transforma isso em `ValueError`.
        """
        try:
            pk = uuid.UUID(force_str(urlsafe_base64_decode(uid)))
        except (ValueError, TypeError):
            return None
        return User.objects.filter(pk=pk, is_active=True).first()


@extend_schema(request=sz.InvitationAcceptSerializer, responses={204: None})
class InvitationAcceptView(APIView):
    """Aceita um convite. Único caminho público para um usuário passar a existir."""

    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = sz.InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            services.accept_invitation(
                token=serializer.validated_data["token"],
                password=serializer.validated_data["password"],
                full_name=serializer.validated_data.get("full_name", ""),
                request=request,
            )
        except services.InvitationError as exc:
            raise ValidationError({"token": [str(exc)]}) from exc

        return Response(status=status.HTTP_204_NO_CONTENT)


class MemberViewSet(TenantViewSet):
    """Membros da organização ativa. Convite cria; aqui só se altera papel ou desativa."""

    serializer_class = sz.MemberSerializer
    permission_classes = [MinRole.at_least(Role.ADMIN)]
    queryset = Membership.objects.select_related("user", "organization")
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def perform_update(self, serializer):
        # A instância é a do serializer, não um segundo `get_object()`: o service altera
        # este mesmo objeto, então a resposta do DRF sai com o papel novo, não o antigo.
        membership = serializer.instance
        write = sz.MemberWriteSerializer(data=self.request.data, partial=True)
        write.is_valid(raise_exception=True)
        new_role = write.validated_data.get("role", membership.role)

        self._guard_last_owner(membership, new_role=new_role)
        services.change_member_role(
            membership=membership,
            new_role=new_role,
            actor=self.request.user,
            request=self.request,
        )

    def perform_destroy(self, instance):
        """Desativa em vez de apagar: o histórico de quem fez o quê precisa continuar legível."""
        self._guard_last_owner(instance, removing=True)
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        record_audit(
            action=AuditLog.Action.DELETE,
            object_type="Membership",
            object_id=instance.pk,
            actor=self.request.user,
            organization=instance.organization,
            changes={"is_active": [True, False]},
            request=self.request,
        )

    def _guard_last_owner(
        self, membership: Membership, *, new_role: str | None = None, removing: bool = False
    ) -> None:
        """Impede que a organização fique sem nenhum OWNER ativo."""
        if membership.role != Role.OWNER:
            return
        if not removing and new_role == Role.OWNER:
            return
        remaining = (
            Membership.objects.filter(
                organization=membership.organization, role=Role.OWNER, is_active=True
            )
            .exclude(pk=membership.pk)
            .exists()
        )
        if not remaining:
            raise ValidationError(
                {"detail": [_("A organização precisa de pelo menos um proprietário ativo.")]}
            )


class InvitationViewSet(TenantViewSet):
    """Convites da organização ativa."""

    serializer_class = sz.InvitationSerializer
    permission_classes = [MinRole.at_least(Role.ADMIN)]
    queryset = Invitation.objects.select_related("organization")
    http_method_names = ["get", "post", "delete", "head", "options"]

    @extend_schema(request=sz.InvitationCreateSerializer, responses={201: sz.InvitationSerializer})
    def create(self, request, *args, **kwargs):
        serializer = sz.InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization: Organization = self.get_organization()
        email = serializer.validated_data["email"].lower()

        if Membership.objects.filter(
            organization=organization, user__email=email, is_active=True
        ).exists():
            raise ValidationError({"email": [_("Este usuário já faz parte da organização.")]})

        invitation, token = Invitation.issue(
            organization=organization,
            email=email,
            role=serializer.validated_data["role"],
            invited_by=request.user,
        )
        record_audit(
            action=AuditLog.Action.CREATE,
            object_type="Invitation",
            object_id=invitation.pk,
            actor=request.user,
            organization=organization,
            changes={"email": email, "role": invitation.role},
            request=request,
        )

        data = sz.InvitationSerializer(invitation).data
        # Única vez em que o token cru existe: o banco só guarda o hash.
        data["token"] = token
        return Response(data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        """Revoga em vez de apagar, e registra — revogar convite é mudança de acesso."""
        instance.revoked_at = timezone.now()
        instance.save(update_fields=["revoked_at", "updated_at"])
        record_audit(
            action=AuditLog.Action.DELETE,
            object_type="Invitation",
            object_id=instance.pk,
            actor=self.request.user,
            organization=instance.organization,
            changes={"revoked": True, "email": instance.email},
            request=self.request,
        )
