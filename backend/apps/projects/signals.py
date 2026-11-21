"""Signals other apps listen to, so this app never imports them (0007).

`project_created(project, template, by)`: sent inside the creating transaction. `boards` makes
the project's first board from the template.
"""

from django.dispatch import Signal

project_created = Signal()
