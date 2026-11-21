from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.realms.urls")),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.integrations.urls")),
    path("api/", include("apps.feasibilities.urls")),
    path("api/", include("apps.integration_logs.urls")),
    path("api/", include("apps.api_clients.urls")),
    path("api/", include("apps.pricebook.urls")),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.boards.urls")),
    path("api/", include("apps.automations.urls")),
    path("api/", include("apps.presence.urls")),
    path("api/", include("apps.analytics.urls")),
    path("api/", include("apps.notifications.urls")),
]
