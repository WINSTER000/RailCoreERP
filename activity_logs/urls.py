from django.urls import path

from . import views

app_name = "activity_logs"

urlpatterns = [
    path("", views.activity_log_list, name="list"),
]
