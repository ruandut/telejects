from django.apps import AppConfig


class BoardsConfig(AppConfig):
    name = "apps.boards"
    label = "boards"

    def ready(self):
        from . import receivers  # noqa: F401  (makes a project's first board)
