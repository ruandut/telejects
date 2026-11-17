"""Viewset and serializer bases that keep an endpoint inside the request's company.

See permissions.py for how the company is chosen. Domain apps build on these, and every endpoint
still gets its own tests in test_isolation.py.
"""

from rest_framework import mixins, serializers, viewsets

from .models import Realm, TenantModel
from .querysets import TenantQuerySet


class RealmScopedMixin:
    """Every lookup (list, detail, custom actions via get_object) starts from
    `in_realm(request.realm)`, and the serializer knows the company."""

    def get_queryset(self):
        return super().get_queryset().in_realm(self.request.realm)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "realm": self.request.realm}


class RealmScopedViewSet(RealmScopedMixin, viewsets.ModelViewSet):
    pass


class RealmScopedReadOnlyViewSet(RealmScopedMixin, viewsets.ReadOnlyModelViewSet):
    pass


class RealmScopedCreateListViewSet(
    RealmScopedMixin, mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    pass


def context_realm(context) -> Realm | None:
    if realm := context.get("realm"):
        return realm
    request = context.get("request")
    return getattr(request, "realm", None)


def _narrow(field, realm):
    """Limit a related field's choices to rows in this company."""
    if isinstance(field, serializers.ManyRelatedField):
        field = field.child_relation
    queryset = getattr(field, "queryset", None)
    if queryset is None or not issubclass(queryset.model, TenantModel):
        return
    if not isinstance(queryset, TenantQuerySet):
        raise TypeError(f"{queryset.model.__name__} must use a TenantQuerySet manager")
    field.queryset = queryset.in_realm(realm) if realm else queryset.none()


class RealmUniqueValidator:
    """Like UniqueTogetherValidator, inside the serializer's company."""

    requires_context = True

    def __init__(self, fields: tuple[str, ...], message: str):
        self.fields = fields
        self.message = message

    def __call__(self, attrs, serializer):
        instance = serializer.instance
        if instance is not None and not any(name in attrs for name in self.fields):
            return
        values = {
            name: attrs[name] if name in attrs else getattr(instance, name, None)
            for name in self.fields
        }
        clash = serializer.Meta.model.objects.in_realm(serializer.realm).filter(**values)
        if instance is not None:
            clash = clash.exclude(pk=instance.pk)
        if clash.exists():
            raise serializers.ValidationError({self.fields[0]: self.message})


class RealmScopedFieldsMixin:
    """Every related field only accepts rows from the request's company."""

    @property
    def realm(self) -> Realm | None:
        return context_realm(self.context)

    def get_fields(self):
        fields = super().get_fields()
        for field in fields.values():
            _narrow(field, self.realm)
        return fields


class RealmScopedInputSerializer(RealmScopedFieldsMixin, serializers.Serializer):
    """A plain (non-model) input serializer whose foreign keys stay inside the company."""


class RealmScopedSerializer(RealmScopedFieldsMixin, serializers.ModelSerializer):
    """A serializer for a TenantModel, or a nested one inside it.

    Foreign keys only accept rows from the request's company, `realm_unique` lists the field
    sets that must be unique within a company, and saving a new row puts it in the company.
    `realm` is never writable: a request can't choose which company a row lands in.
    """

    realm_unique: dict[tuple[str, ...], str] = {}

    def get_fields(self):
        fields = super().get_fields()
        if "realm" in fields:
            fields["realm"].read_only = True
        return fields

    def get_validators(self):
        return [
            *super().get_validators(),
            *(RealmUniqueValidator(names, message) for names, message in self.realm_unique.items()),
        ]

    def save(self, **kwargs):
        if self.instance is None and issubclass(self.Meta.model, TenantModel):
            kwargs["realm"] = self.realm
        return super().save(**kwargs)
