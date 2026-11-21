from rest_framework import serializers

from apps.realms.access import RealmScopedInputSerializer, RealmScopedSerializer
from apps.realms.models import RealmMembership

from .models import Level, Project, ProjectMember


class PersonSerializer(serializers.ModelSerializer):
    """Someone in the company, as pickers show them. `id` is the membership's id."""

    name = serializers.CharField(source="display_name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = RealmMembership
        fields = ["id", "name", "email"]
        read_only_fields = fields


class ProjectSerializer(RealmScopedSerializer):
    my_level = serializers.CharField(read_only=True)
    owner_name = serializers.SerializerMethodField()
    # Set by the list view: item counts and progress, filled in by the boards app's totals.
    template = serializers.CharField(write_only=True, required=False, default="blank")

    realm_unique = {("name",): "There is already a project with this name."}

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "client",
            "description",
            "status",
            "colour",
            "owner",
            "owner_name",
            "start_date",
            "end_date",
            "created_at",
            "updated_at",
            "my_level",
            "template",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "my_level", "owner_name"]
        extra_kwargs = {"owner": {"queryset": RealmMembership.objects.none(), "required": False}}

    def get_fields(self):
        fields = super().get_fields()
        realm = self.realm
        owner = fields["owner"]
        owner.queryset = (
            RealmMembership.objects.in_realm(realm).current() if realm else owner.queryset.none()
        )
        owner.allow_null = True
        return fields

    def get_owner_name(self, project) -> str | None:
        return project.owner.display_name if project.owner_id else None

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the project a name.")
        return value


class ProjectMemberSerializer(serializers.ModelSerializer):
    person = PersonSerializer(source="membership", read_only=True)

    class Meta:
        model = ProjectMember
        fields = ["id", "person", "level", "added_at"]
        read_only_fields = fields


class ShareSerializer(RealmScopedInputSerializer):
    membership = serializers.PrimaryKeyRelatedField(queryset=RealmMembership.objects.none())
    level = serializers.ChoiceField(choices=Level.choices, allow_null=True)

    def get_fields(self):
        fields = super().get_fields()
        realm = self.realm
        fields["membership"].queryset = (
            RealmMembership.objects.in_realm(realm).current()
            if realm
            else RealmMembership.objects.none()
        )
        return fields


class AccessSerializer(ShareSerializer):
    """Sharing from User management: one person, one project."""

    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())
