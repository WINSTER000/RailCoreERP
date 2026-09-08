"""Root URL configuration for RailCore ERP."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView

admin.site.site_header = "RailCore ERP Administration"
admin.site.site_title = "RailCore ERP"
admin.site.index_title = "Railway operations control panel"

urlpatterns = [
    # "/" always lands on the dashboard; the dashboard itself requires a login,
    # so anonymous visitors are forwarded to the sign-in screen.
    path("", RedirectView.as_view(pattern_name="dashboard:home", permanent=False), name="root"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("railway/", include("railway.urls")),
    path("notifications/", include("notifications.urls")),
    path("activity/", include("activity_logs.urls")),
]

# Uploaded profile images are served by Django. On a single-instance Render
# deployment this keeps the demo self-contained; a system with heavy media use
# would front these files with object storage instead.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")
