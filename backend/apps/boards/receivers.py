"""A new project gets its first board, from the template it was created with (none for
"none": a project imported from a file gets its boards from the file)."""

from django.dispatch import receiver

from apps.projects.signals import project_created

from . import services


@receiver(project_created, dispatch_uid="boards-first-board")
def make_first_board(sender, project, template, by, **kwargs):
    if template == "none":
        return  # its boards come from a file next (file_import.py)
    services.create_board(project, template=template, actor=services.Actor(membership=by))
