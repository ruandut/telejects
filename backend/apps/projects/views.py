"""Projects (0007). A project is looked up through `in_realm(...).visible_to(membership)`, so a
project the person may not open is a 404, like another company's. Changing one needs manage
level on it; creating, deleting and sharing from User management need `projects.manage`."""

from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.realms.access import RealmScopedMixin
from apps.realms.models import RealmMembership
from apps.realms.permissions import HasRealmPermission, InRealm

from . import access, services
from .models import Level, Project, ProjectMember
from .querysets import manages_all
from .serializers import (
    AccessSerializer,
    PersonSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
    ShareSerializer,
)


class ProjectViewSet(RealmScopedMixin, viewsets.ModelViewSet):
    permission_classes = [InRealm, HasRealmPermission("projects.view")]
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    lookup_value_regex = r"\d+"
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        membership = self.request.membership
        projects = (
            super()
            .get_queryset()
            .visible_to(membership)
            .with_level(membership)
            .select_related("owner__user")
        )
        if self.action == "list":
            if self.request.query_params.get("archived") != "1":
                projects = projects.current()
            projects = projects.search(self.request.query_params.get("search", ""))
        return projects.order_by("name", "id")

    def _manager_only(self):
        if not manages_all(self.request.membership):
            raise PermissionDenied("You need permission to manage projects.")

    def perform_create(self, serializer):
        self._manager_only()
        data = dict(serializer.validated_data)
        template = data.pop("template", "blank")
        serializer.instance = services.create_project(
            self.request.realm, self.request.membership, template=template, **data
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        fresh = self.get_queryset().get(pk=serializer.instance.pk)
        return Response(self.get_serializer(fresh).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        project = self.get_object()
        access.require(request.membership, project, Level.MANAGE)
        serializer = self.get_serializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = {k: v for k, v in serializer.validated_data.items() if k != "template"}
        services.update_project(project, **data)
        return Response(self.get_serializer(self.get_queryset().get(pk=project.pk)).data)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        self._manager_only()
        services.delete_project(project)
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- who may work on it ---------------------------------------------------------------

    @action(detail=True, methods=["get", "post"])
    def members(self, request, pk=None):
        """GET: who the project is shared with. POST {membership, level|null}: share it, change
        someone's level, or (null) stop sharing it with them. Sharing needs manage level."""
        project = self.get_object()
        if request.method == "POST":
            access.require(request.membership, project, Level.MANAGE)
            serializer = ShareSerializer(data=request.data, context=self.get_serializer_context())
            serializer.is_valid(raise_exception=True)
            person = serializer.validated_data["membership"]
            level = serializer.validated_data["level"]
            if level is None:
                services.unshare(project, person)
            else:
                services.share(project, person, level)
        rows = (
            ProjectMember.objects.in_realm(request.realm)
            .of_project(project)
            .select_related("membership__user")
        )
        return Response(ProjectMemberSerializer(rows, many=True).data)

    @action(detail=True, methods=["get"])
    def people(self, request, pk=None):
        """Everyone who can open the project: who a people column or a mention can name."""
        project = self.get_object()
        return Response(PersonSerializer(people_of(project), many=True).data)

    @action(detail=True, methods=["get"])
    def candidates(self, request, pk=None):
        """The company's people, to share the project with. Needs manage level on it."""
        project = self.get_object()
        access.require(request.membership, project, Level.MANAGE)
        people = (
            RealmMembership.objects.in_realm(request.realm)
            .current()
            .select_related("user")
            .order_by("name", "user__email", "id")
        )
        return Response(PersonSerializer(people, many=True).data)


def people_of(project: Project):
    """Active people who can open this project: managers of every project, and those it is
    shared with."""
    memberships = (
        RealmMembership.objects.in_realm(project.realm_id)
        .active()
        .select_related("user", "role")
        .order_by("name", "user__email", "id")
    )
    shared = set(
        ProjectMember.objects.in_realm(project.realm_id)
        .of_project(project)
        .values_list("membership_id", flat=True)
    )
    return [m for m in memberships if m.pk in shared or manages_all(m)]


class ProjectAccessViewSet(viewsets.ViewSet):
    """Sharing from User management: which projects one person can open, and at what level.
    Needs `projects.manage`."""

    permission_classes = [InRealm, HasRealmPermission("projects.manage")]

    def list(self, request):
        membership = (
            RealmMembership.objects.in_realm(request.realm)
            .current()
            .by_id(request.query_params.get("membership"))
        )
        if membership is None:
            raise Http404
        rows = (
            ProjectMember.objects.in_realm(request.realm)
            .of_membership(membership)
            .select_related("project")
            .order_by("project__name", "id")
        )
        return Response(
            {
                "manages_all": manages_all(membership),
                "projects": [
                    {"project": r.project_id, "name": r.project.name, "level": r.level}
                    for r in rows
                ],
            }
        )

    def create(self, request):
        context = {"request": request, "realm": request.realm}
        serializer = AccessSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["level"] is None:
            services.unshare(data["project"], data["membership"])
        else:
            services.share(data["project"], data["membership"], data["level"])
        return Response(status=status.HTTP_204_NO_CONTENT)
