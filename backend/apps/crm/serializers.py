from __future__ import annotations

from rest_framework import serializers

from apps.crm.models import Interaction, Lead, Note, Pipeline, PipelineStage, SuppressionEntry, Task


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


class NoteSerializer(serializers.ModelSerializer):
    author_email = serializers.CharField(source="author.email", read_only=True, default=None)

    class Meta:
        model = Note
        fields = ["id", "body", "author_email", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ["id", "lead", "title", "due_at", "status", "assignee"]


class SuppressionEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = SuppressionEntry
        fields = ["id", "identifier_kind", "identifier_value", "reason", "created_at"]
