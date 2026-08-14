"""Serializers de contas.

Validação sempre no backend (CLAUDE.md): nada do que chega do cliente é confiável.
"""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import Invitation, Membership, Organization, Role, User


def _check_password_strength(password: str, user: User | None = None) -> str:
    """Aplica os validadores de senha do Django e traduz o erro para o formato do DRF."""
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return password


class DetailSerializer(serializers.Serializer):
    """Resposta simples de `{"detail": "..."}`, usada no schema OpenAPI."""

    detail = serializers.CharField()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "timezone"]
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "organization", "role", "is_active", "joined_at"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name"]
        read_only_fields = fields


class MeSerializer(serializers.Serializer):
    """Quem sou eu, onde estou e o que posso fazer."""

    user = UserSerializer()
    organization = OrganizationSerializer(allow_null=True)
    role = serializers.CharField(allow_null=True)
    memberships = MembershipSerializer(many=True)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class SwitchOrganizationSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value: str) -> str:
        return _check_password_strength(value, self.context["request"].user)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value: str) -> str:
        return _check_password_strength(value)


class MemberWriteSerializer(serializers.Serializer):
    """Alteração de papel de um membro já existente."""

    role = serializers.ChoiceField(choices=Role.choices)


class MemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "is_active", "joined_at"]
        read_only_fields = ["id", "user", "joined_at"]


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "expires_at", "accepted_at", "revoked_at", "created_at"]
        read_only_fields = ["id", "expires_at", "accepted_at", "revoked_at", "created_at"]


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices, default=Role.VIEWER)


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value: str) -> str:
        return _check_password_strength(value)
