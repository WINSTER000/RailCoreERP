"""URL configuration for the railway operations module."""

from django.urls import path

from . import views

app_name = "railway"

urlpatterns = [
    # -- Trains ----------------------------------------------------------
    path("trains/", views.train_list, name="train_list"),
    path("trains/add/", views.train_create, name="train_add"),
    path("trains/archive/", views.train_archive, name="train_archive"),
    path("trains/<int:pk>/", views.train_detail, name="train_detail"),
    path("trains/<int:pk>/edit/", views.train_update, name="train_edit"),
    path("trains/<int:pk>/delete/", views.train_delete, name="train_delete"),
    path("trains/<int:pk>/restore/", views.train_restore, name="train_restore"),
    # -- Routes ----------------------------------------------------------
    path("routes/", views.route_list, name="route_list"),
    path("routes/add/", views.route_create, name="route_add"),
    path("routes/<int:pk>/", views.route_detail, name="route_detail"),
    path("routes/<int:pk>/edit/", views.route_update, name="route_edit"),
    path("routes/<int:pk>/delete/", views.route_delete, name="route_delete"),
    # -- Schedules -------------------------------------------------------
    path("schedules/", views.schedule_list, name="schedule_list"),
    path("schedules/add/", views.schedule_create, name="schedule_add"),
    path("schedules/<int:pk>/", views.schedule_detail, name="schedule_detail"),
    path("schedules/<int:pk>/edit/", views.schedule_update, name="schedule_edit"),
    path("schedules/<int:pk>/delete/", views.schedule_delete, name="schedule_delete"),
    path("schedules/<int:pk>/cancel/", views.schedule_toggle_cancel, name="schedule_cancel"),
    # -- Stations --------------------------------------------------------
    path("stations/", views.station_list, name="station_list"),
    path("stations/add/", views.station_create, name="station_add"),
    path("stations/<int:pk>/", views.station_detail, name="station_detail"),
    path("stations/<int:pk>/edit/", views.station_update, name="station_edit"),
    path("stations/<int:pk>/delete/", views.station_delete, name="station_delete"),
    # -- Platforms -------------------------------------------------------
    path("platforms/", views.platform_list, name="platform_list"),
    path("platforms/add/", views.platform_create, name="platform_add"),
    path("platforms/<int:pk>/edit/", views.platform_update, name="platform_edit"),
    path("platforms/<int:pk>/delete/", views.platform_delete, name="platform_delete"),
    # -- Route stations --------------------------------------------------
    path("route-stations/", views.route_station_list, name="route_station_list"),
    path("route-stations/add/", views.route_station_create, name="route_station_add"),
    path("route-stations/<int:pk>/edit/", views.route_station_update, name="route_station_edit"),
    path("route-stations/<int:pk>/delete/", views.route_station_delete, name="route_station_delete"),
]
