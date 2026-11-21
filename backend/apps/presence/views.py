"""Presence on a board (0007): who else has it open. Anyone who can open the board sees it,
and only the board's own visitors are listed."""

from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.boards.views import board_for
from apps.realms.permissions import HasRealmPermission, InRealm

from . import services


class Heartbeat(serializers.Serializer):
    board = serializers.IntegerField()
    tab = serializers.RegexField(r"^[A-Za-z0-9_-]{4,40}$")
    item = serializers.IntegerField(required=False, allow_null=True)
    column = serializers.CharField(max_length=40, required=False, allow_blank=True, allow_null=True)


class PresenceViewSet(viewsets.ViewSet):
    permission_classes = [InRealm, HasRealmPermission("projects.view", write="projects.view")]

    def list(self, request):
        board, _ = board_for(request, request.query_params.get("board"))
        return Response(services.present(board))

    def create(self, request):
        data = Heartbeat(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        board, _ = board_for(request, data["board"])
        services.heartbeat(
            board, request.membership, data["tab"], data.get("item"), data.get("column") or ""
        )
        return Response(services.present(board))

    @action(detail=False, methods=["post"])
    def leave(self, request):
        data = Heartbeat(data=request.data)
        data.is_valid(raise_exception=True)
        board, _ = board_for(request, data.validated_data["board"])
        services.leave(board, request.membership, data.validated_data["tab"])
        return Response(status=204)
