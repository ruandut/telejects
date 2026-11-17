"""Live topics for feasibilities (see apps/realms/live.py).

`feasibility_run` pushes the lines that just finished, with the run's counts, to whoever has the
run open. They are loaded with the same scoped queryset and serializers as
`GET /api/feasibilities/runs/<id>/sites/`, for the subscriber's own membership, so the socket
shows exactly what the API would.
"""

from apps.realms.live import Topic

from .models import FeasibilityRun, RunSite
from .serializers import RunSerializer, SiteSerializer


def _run(membership, run_id):
    # Project visibility (later) chains here, as in views.RunViewSet.get_queryset.
    return FeasibilityRun.objects.in_realm(membership.realm_id).by_id(run_id)


def _authorize(membership, run_id) -> bool:
    return _run(membership, run_id) is not None


def _render(membership, run_id, site_ids):
    run = _run(membership, run_id)
    if run is None:
        return None
    context = {"realm": membership.realm}
    sites = RunSite.objects.in_realm(membership.realm_id).of_run(run).filter(id__in=site_ids)
    return {
        "run": RunSerializer(run, context=context).data,
        "sites": SiteSerializer(sites.with_results(), many=True, context=context).data,
    }


TOPICS = {
    "feasibility_runs": Topic(permission="feasibilities.view"),
    "feasibility_run": Topic(
        permission="feasibilities.view", subject=True, authorize=_authorize, render=_render
    ),
}
