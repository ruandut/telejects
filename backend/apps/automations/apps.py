from django.apps import AppConfig


class AutomationsConfig(AppConfig):
    name = "apps.automations"
    label = "automations"

    def ready(self):
        from . import receivers  # noqa: F401  (listens to the boards' signals)
