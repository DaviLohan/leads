from __future__ import annotations

from rest_framework import serializers

from apps.companies.queries import OPPORTUNITY_OPEN
from apps.crm.models import (
    CompanyList,
    Interaction,
    Lead,
    Note,
    Pipeline,
    PipelineStage,
    SuppressionEntry,
    Task,
)


class PipelineStageSerializer(serializers.ModelSerializer):
    lead_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PipelineStage
        fields = ["id", "code", "name", "position", "is_terminal", "is_won", "lead_count"]


class PipelineSerializer(serializers.ModelSerializer):
    stages = PipelineStageSerializer(many=True, read_only=True)

    class Meta:
        model = Pipeline
        fields = ["id", "name", "is_default", "stages"]


class InteractionSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.email", read_only=True, default=None)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Interaction
        fields = [
            "id",
            "kind",
            "kind_label",
            "description",
            "outcome",
            "next_action",
            "next_action_at",
            "occurred_at",
            "author_name",
        ]
        # Append-only: o histórico não se reescreve. Quem grava é o serviço.
        read_only_fields = ["occurred_at"]


class LeadSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    # Contato e localização vêm anotados pela view — o lead é uma linha de fila de ligações,
    # e o telefone é o dado que faz a fila andar.
    phone = serializers.CharField(read_only=True, default=None)
    whatsapp = serializers.CharField(read_only=True, default=None)
    city = serializers.CharField(source="city_name", read_only=True, default=None)
    uf = serializers.CharField(read_only=True, default=None)
    opportunities = serializers.SerializerMethodField()
    stage_code = serializers.CharField(source="stage.code", read_only=True)
    stage_name = serializers.CharField(source="stage.name", read_only=True)
    owner_email = serializers.CharField(source="owner.email", read_only=True, default=None)
    # O score atual da empresa, ao lado do que ela tinha na entrada: ver os dois juntos é o
    # que mostra que a empresa melhorou — e que a oportunidade encolheu.
    current_score = serializers.IntegerField(
        source="company.score.value", read_only=True, default=None
    )

    class Meta:
        model = Lead
        fields = [
            "id",
            "company",
            "company_name",
            "phone",
            "whatsapp",
            "city",
            "uf",
            "opportunities",
            "stage",
            "stage_code",
            "stage_name",
            "owner",
            "owner_email",
            "score_snapshot",
            "current_score",
            "last_contacted_at",
            "next_action_at",
            "created_at",
        ]
        read_only_fields = ["score_snapshot", "last_contacted_at"]

    def get_opportunities(self, obj) -> list[dict[str, str]]:
        """As oportunidades abertas da empresa — o motivo de a conversa existir.

        A anotação de retorno não é enfeite: é dela que o drf-spectacular tira o tipo do
        campo no schema. Sem ela, o campo vira `string` e a checagem de deploy da CI falha.
        """
        return [
            {"code": o.type.code, "name": o.type.name}
            for o in obj.company.opportunities.all()
            if o.status == OPPORTUNITY_OPEN
        ]


class NoteSerializer(serializers.ModelSerializer):
    author_email = serializers.CharField(source="author.email", read_only=True, default=None)

    class Meta:
        model = Note
        fields = ["id", "body", "author_email", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["id", "lead", "title", "due_at", "status", "assignee"]


class CompanyListSerializer(serializers.ModelSerializer):
    company_count = serializers.IntegerField(read_only=True)
    created_by_email = serializers.CharField(
        source="created_by.email", read_only=True, default=None
    )

    class Meta:
        model = CompanyList
        fields = [
            "id",
            "name",
            "description",
            "company_count",
            "created_by_email",
            "created_at",
            "updated_at",
        ]


class SuppressionEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = SuppressionEntry
        fields = ["id", "identifier_kind", "identifier_value", "reason", "created_at"]
