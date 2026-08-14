from __future__ import annotations

from rest_framework import serializers

from apps.companies.models import Category


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "slug", "name", "parent"]
