"""Live topics for integrations (see apps/realms/live.py). Connections change rarely, so the
socket only says "changed" and the tab refetches through the API."""

from apps.realms.live import Topic

TOPICS = {"integrations": Topic(permission="integrations.view")}
