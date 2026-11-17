"""Websocket routes. Every consumer follows the API's access rules (root CLAUDE.md)."""

from django.urls import path

from .consumers import RealmEventsConsumer

websocket_urlpatterns: list = [path("ws/events/", RealmEventsConsumer.as_asgi())]
