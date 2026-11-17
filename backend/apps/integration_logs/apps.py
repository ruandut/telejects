from django.apps import AppConfig
from django.conf import settings


class IntegrationLogsConfig(AppConfig):
    """Every request made to a provider, and its answer, kept per company up to a limit (0005).

    Sits below `integrations` and `feasibilities` (they write to it), so it refers to their rows
    by id, with a snapshot of the connection's name."""

    name = "apps.integration_logs"
    label = "integration_logs"

    @property
    def default_limit(self) -> int:
        """How many requests a company keeps unless staff set its own (LogRetention)."""
        return settings.INTEGRATION_LOGS_DEFAULT_LIMIT
