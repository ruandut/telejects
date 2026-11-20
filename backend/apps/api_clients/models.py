"""API clients (0006): a company's machine access, through OAuth2 client credentials.

Each client is a django-oauth-toolkit Application owned by one company. Its permissions are our
permission codes, chosen by the admin who made it from their own. A request made with its token
works in its company only, and only within those permissions, for as long as the client isn't
revoked and its maker is still an active member who has them.
"""

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.realms.models import TenantModel

from .querysets import ApiClientQuerySet


class ApiClient(TenantModel):
    name = models.CharField(max_length=100)
    # SET_NULL: revoking deletes the Application (and with it every token); the row stays.
    application = models.OneToOneField(
        settings.OAUTH2_PROVIDER_APPLICATION_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="api_client",
    )
    client_id = models.CharField(max_length=100, unique=True)
    permissions = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = ApiClientQuerySet.as_manager()

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["realm", "name"],
                condition=models.Q(revoked_at__isnull=True),
                name="api_client_name_in_realm",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.application_id is not None


@receiver(post_delete, sender=ApiClient)
def _delete_application(sender, instance: ApiClient, **kwargs):
    """A client deleted with its company takes its OAuth application (and tokens) with it."""
    if instance.application_id:
        instance.__class__.application.field.related_model.objects.filter(
            pk=instance.application_id
        ).delete()
