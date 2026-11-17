"""The websocket a signed-in tab keeps open for live updates in its company.

The socket follows the API's rules (root CLAUDE.md, Multi-tenancy):
- A browser can't send the JWT with the handshake, so the first message must be
  {"type": "auth", "token": <access token>, "realm": <company id or null>}. The token must be
  valid and current (not from before a password change), and the user an active member of the
  company, as InRealm requires.
- Then the tab subscribes: {"type": "subscribe", "topic": "...", "subject": <id or null>}. A
  topic (live.py) names the permission it needs, and a subject is looked up through the owning
  app's scoped queryset, so another company's run is refused exactly like a missing one.
- What it sends is built per subscriber by the topic's `render`, with the API's own queryset and
  serializer. Membership and permission are checked again before every send: someone removed
  is disconnected, and someone who lost the permission is unsubscribed.
- Events are gathered for about a second per subscription, so a large run doesn't flood it.
"""

import asyncio
import json
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth import get_user_model
from rest_framework.renderers import JSONRenderer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from . import listener
from .events import group_name
from .live import topics
from .models import RealmMembership

AUTH_SECONDS = 10
FLUSH_SECONDS = 1.0
MAX_SUBSCRIPTIONS = 20
# Close codes the frontend acts on: get a fresh token and reconnect, or stop trying.
UNAUTHENTICATED = 4401
NOT_A_MEMBER = 4403


def _membership(user_id: int, realm_id) -> RealmMembership | None:
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return None
    memberships = RealmMembership.objects
    if realm_id is None:
        return memberships.default_for(user)
    return memberships.of_user(user).in_realm(realm_id).first()


@database_sync_to_async
def _admit(token: str, realm_id) -> tuple[int, RealmMembership | None, float]:
    """(close code or 0, membership, seconds until the token expires)."""
    try:
        access = AccessToken(token)
    except TokenError:
        return UNAUTHENTICATED, None, 0
    user = get_user_model().objects.filter(pk=access.get("user_id"), is_active=True).first()
    # A token from before a password change no longer signs anyone in (0002).
    if user is None or access.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(
        user.password
    ):
        return UNAUTHENTICATED, None, 0
    membership = _membership(user.pk, realm_id)
    if membership is None:
        return NOT_A_MEMBER, None, 0
    return 0, membership, max(float(access["exp"]) - time.time(), 0)


@database_sync_to_async
def _current(user_id: int, realm_id: int) -> RealmMembership | None:
    return _membership(user_id, realm_id)


@database_sync_to_async
def _authorized(membership: RealmMembership, name: str, subject) -> bool:
    topic = topics().get(name)
    if topic is None or not membership.has_perm(topic.permission):
        return False
    if topic.subject:
        return subject is not None and bool(topic.authorize(membership, subject))
    return subject is None


@database_sync_to_async
def _render(membership: RealmMembership, name: str, subject, items):
    topic = topics()[name]
    if topic.render is None or items is None:
        return None
    data = topic.render(membership, subject, items)
    # Rendered as the API renders it (decimals, dates), so both send the same JSON.
    return None if data is None else json.loads(JSONRenderer().render(data))


def _subject(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError
    return int(value)


class RealmEventsConsumer(AsyncJsonWebsocketConsumer):
    group: str | None = None
    membership: RealmMembership | None = None
    _deadline: asyncio.Task | None = None
    _flusher: asyncio.Task | None = None

    async def connect(self):
        self.subscriptions: set[tuple[str, int | None]] = set()
        # (topic, subject) -> changed ids, or None for "everything may have changed".
        self.pending: dict[tuple[str, int | None], set[int] | None] = {}
        await self.accept()
        self._close_in(AUTH_SECONDS)

    def _close_in(self, seconds: float) -> None:
        """Close as unauthenticated after a while: no token arrived, or the token ran out."""
        if self._deadline is not None:
            self._deadline.cancel()

        async def close_later():
            await asyncio.sleep(seconds)
            await self.close(code=UNAUTHENTICATED)

        self._deadline = asyncio.ensure_future(close_later())

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            return
        if self.membership is None:
            await self._authenticate(content)
            return
        kind = content.get("type")
        if kind not in ("subscribe", "unsubscribe"):
            return
        name = content.get("topic")
        try:
            subject = _subject(content.get("subject"))
        except TypeError, ValueError:
            subject = None
            name = None
        key = (name, subject)
        if kind == "unsubscribe":
            self.subscriptions.discard(key)
            self.pending.pop(key, None)
            return
        allowed = (
            isinstance(name, str)
            and len(self.subscriptions) < MAX_SUBSCRIPTIONS
            and await _authorized(self.membership, name, subject)
        )
        reply = {"topic": name if isinstance(name, str) else None, "subject": subject}
        if not allowed:
            await self.send_json({"type": "refused", **reply})
            return
        self.subscriptions.add(key)
        await self.send_json({"type": "subscribed", **reply})

    async def _authenticate(self, content):
        if content.get("type") != "auth" or not isinstance(content.get("token"), str):
            await self.close(code=UNAUTHENTICATED)
            return
        refused, membership, lifetime = await _admit(content["token"], content.get("realm"))
        if refused:
            await self.close(code=refused)
            return
        self.membership = membership
        self.group = group_name(membership.realm_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        listener.ensure_listening()
        # The socket lives as long as the token that opened it; the tab then reconnects with a
        # fresh one, and everything is checked again.
        self._close_in(lifetime)
        await self.send_json({"type": "ready", "realm": membership.realm_id})

    async def realm_event(self, event):
        if self.membership is None or event.get("realm") != self.membership.realm_id:
            return
        key = (event["topic"], event.get("subject"))
        if key not in self.subscriptions:
            return
        items = event.get("items") if event.get("has_items") else None
        if key in self.pending:
            known = self.pending[key]
            self.pending[key] = None if known is None or items is None else known | set(items)
        else:
            self.pending[key] = None if items is None else set(items)
        if self._flusher is None or self._flusher.done():
            self._flusher = asyncio.ensure_future(self._flush_later())

    async def _flush_later(self):
        await asyncio.sleep(FLUSH_SECONDS)
        await self.flush()

    async def flush(self):
        """Send what gathered, after checking again that this person may still see it."""
        pending, self.pending = self.pending, {}
        if not pending or self.membership is None:
            return
        membership = await _current(self.membership.user_id, self.membership.realm_id)
        if membership is None:
            await self.close(code=NOT_A_MEMBER)
            return
        self.membership = membership
        for (name, subject), items in pending.items():
            if (name, subject) not in self.subscriptions:
                continue
            if not await _authorized(membership, name, subject):
                self.subscriptions.discard((name, subject))
                await self.send_json({"type": "refused", "topic": name, "subject": subject})
                continue
            data = await _render(membership, name, subject, sorted(items) if items else items)
            message = {"topic": name, "subject": subject}
            if data is None:
                await self.send_json({"type": "changed", **message})
            else:
                await self.send_json({"type": "data", **message, "data": data})

    async def disconnect(self, code):
        for task in (self._deadline, self._flusher):
            if task is not None:
                task.cancel()
        if self.group is not None:
            await self.channel_layer.group_discard(self.group, self.channel_name)
