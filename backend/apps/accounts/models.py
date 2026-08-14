"""Contas: usuário, organização, vínculo e convite.

Fronteira de tenancy em ADR-0007: dado comercial pertence à `Organization`; dado público
sobre empresas é global. Papéis e hierarquia de RBAC vivem em `Role`.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.core.ids import uuid7
from apps.core.models import BaseModel, TenantQuerySet

INVITATION_TTL = timedelta(days=7)

if TYPE_CHECKING:
    _ManagerBase = BaseUserManager["User"]
else:
    _ManagerBase = BaseUserManager


class UserManager(_ManagerBase):
    """Login por e-mail, não por username."""

    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("E-mail é obrigatório.")
        extra_fields.setdefault("is_active", True)
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)  # hasher do Django; nunca algoritmo próprio
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields.get("is_staff") or not extra_fields.get("is_superuser"):
            raise ValueError("Superusuário precisa de is_staff e is_superuser.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    email = models.EmailField(_("e-mail"), unique=True)
    full_name = models.CharField(_("nome completo"), max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = _("usuário")
        verbose_name_plural = _("usuários")
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.email


class Role(models.TextChoices):
    """Papéis do RBAC, do mais para o menos privilegiado.

    A ordem desta enumeração é a hierarquia usada em `apps.accounts.permissions`.
    """

    OWNER = "OWNER", _("Proprietário")
    ADMIN = "ADMIN", _("Administrador")
    MANAGER = "MANAGER", _("Gestor")
    SALES = "SALES", _("Comercial")
    VIEWER = "VIEWER", _("Leitor")


# Quanto maior o número, mais privilégio. Comparar posições evita uma tabela de permissão
# por endpoint (ADR-0008 aplica a mesma ideia às regras de score).
ROLE_RANK: dict[str, int] = {
    Role.VIEWER: 0,
    Role.SALES: 1,
    Role.MANAGER: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


class Organization(BaseModel):
    """Tenant. Todo dado comercial pende daqui (ADR-0007)."""

    name = models.CharField(_("nome"), max_length=150)
    slug = models.SlugField(_("identificador"), max_length=160, unique=True)
    timezone = models.CharField(max_length=64, default="America/Sao_Paulo")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("organização")
        verbose_name_plural = _("organizações")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.slug:
            return super().save(*args, **kwargs)

        self.slug = self._build_readable_slug()
        try:
            with transaction.atomic():
                return super().save(*args, **kwargs)
        except IntegrityError:
            # Outra transação levou o mesmo slug entre a checagem e o INSERT. Quem arbitra
            # é a UniqueConstraint, não um `if exists` em Python (CLAUDE.md) — e o desempate
            # é aleatório de propósito: repetir a contagem colidiria de novo.
            self.slug = f"{self._slug_base()[:140]}-{secrets.token_hex(3)}"
            return super().save(*args, **kwargs)

    def _slug_base(self) -> str:
        return slugify(self.name)[:150] or "org"

    def _build_readable_slug(self) -> str:
        """Primeira tentativa, legível. A unicidade real é garantida pelo banco."""
        base = self._slug_base()
        candidate = base
        suffix = 2
        while Organization.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate


class Membership(BaseModel):
    """Vínculo entre usuário e organização, com o papel que ele exerce nela."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.VIEWER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    objects = TenantQuerySet.as_manager()

    class Meta:
        verbose_name = _("vínculo")
        verbose_name_plural = _("vínculos")
        ordering = ["organization__name", "user__email"]
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="uniq_user_organization"),
        ]
        indexes = [models.Index(fields=["organization", "role"])]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.organization.name} ({self.role})"

    @property
    def rank(self) -> int:
        return ROLE_RANK.get(self.role, -1)


def _hash_token(token: str) -> str:
    """SHA-256 do token de convite.

    O token é aleatório de 256 bits, não uma senha escolhida por humano — não há espaço de
    busca para força bruta, então hash rápido basta e mantém a verificação barata.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class Invitation(BaseModel):
    """Convite para entrar em uma organização.

    Não existe cadastro público: um usuário só nasce por comando de gestão (o primeiro
    OWNER) ou aceitando um convite. O banco guarda apenas o hash do token — o valor cru
    existe uma única vez, na resposta da criação.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField(_("e-mail"))
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.VIEWER)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    invited_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="invitations_sent"
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="invitations_accepted"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        verbose_name = _("convite")
        verbose_name_plural = _("convites")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "email"])]

    def __str__(self) -> str:
        return f"{self.email} → {self.organization.name}"

    @classmethod
    def issue(
        cls,
        *,
        organization: Organization,
        email: str,
        role: str,
        invited_by: User | None = None,
    ) -> tuple[Invitation, str]:
        """Cria o convite e devolve `(convite, token_cru)`. O token não é recuperável depois."""
        token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            organization=organization,
            email=email.lower().strip(),
            role=role,
            token_hash=_hash_token(token),
            invited_by=invited_by,
            expires_at=timezone.now() + INVITATION_TTL,
        )
        return invitation, token

    @classmethod
    def find_usable(cls, token: str) -> Invitation | None:
        """Devolve o convite ativo correspondente ao token, ou `None`."""
        invitation = cls.objects.filter(token_hash=_hash_token(token)).first()
        return invitation if invitation and invitation.is_usable else None

    @property
    def is_usable(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
            and self.organization.is_active
        )
