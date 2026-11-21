"""Automations (0007). Seen by anyone who can open the board; created, changed and deleted with
manage level on its project. An automation is looked up through `visible_to(membership)`, so
one in a project the person can't open is a 404."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.boards.views import board_for
from apps.projects import access
from apps.projects.models import Level
from apps.realms.access import RealmScopedMixin
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services
from .models import Automation, AutomationRun
from .recipes import catalogue
from .serializers import AutomationInputSerializer, AutomationSerializer, RunSerializer


class AutomationViewSet(RealmScopedMixin, viewsets.GenericViewSet):
    permission_classes = [InRealm, HasRealmPermission("projects.view", write="projects.view")]
    queryset = Automation.objects.select_related("board__project", "created_by__user")
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return super().get_queryset().visible_to(self.request.membership)

    def _automation(self, needed=Level.VIEW):
        automation = self.get_object()
        access.require(self.request.membership, automation.board.project, needed)
        return automation

    def _input(self, partial=False):
        serializer = AutomationInputSerializer(data=self.request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return {k: v for k, v in serializer.validated_data.items() if k != "board"}

    def list(self, request):
        board, _ = board_for(request, request.query_params.get("board"))
        rows = self.get_queryset().filter(board_id=board.pk).order_by("created_at", "id")
        return Response(AutomationSerializer(rows, many=True).data)

    def create(self, request):
        board, _ = board_for(request, request.data.get("board"), Level.MANAGE)
        automation = services.create_automation(board, request.membership, self._input())
        return Response(AutomationSerializer(automation).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return Response(AutomationSerializer(self._automation()).data)

    def partial_update(self, request, pk=None):
        automation = self._automation(Level.MANAGE)
        automation = services.update_automation(
            automation, request.membership, self._input(partial=True)
        )
        return Response(AutomationSerializer(automation).data)

    def destroy(self, request, pk=None):
        services.delete_automation(self._automation(Level.MANAGE))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def runs(self, request, pk=None):
        automation = self._automation()
        rows = AutomationRun.objects.in_realm(request.realm).of_automation(automation)[:100]
        return Response(RunSerializer(rows, many=True).data)

    @action(detail=False, methods=["get"])
    def recipes(self, request):
        return Response(catalogue())
