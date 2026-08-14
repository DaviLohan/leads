from __future__ import annotations

from rest_framework import serializers

from apps.geography.models import City, State


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ["id", "ibge_code", "uf", "name", "region"]


class CitySerializer(serializers.ModelSerializer):
    uf = serializers.CharField(source="state.uf", read_only=True)
    state_name = serializers.CharField(source="state.name", read_only=True)

    class Meta:
        model = City
        # `centroid` fica de fora enquanto for sempre nulo (ver City no models.py). Entra na
        # Etapa 8, junto com quem o preenche.
        fields = ["id", "ibge_code", "name", "state", "uf", "state_name"]
