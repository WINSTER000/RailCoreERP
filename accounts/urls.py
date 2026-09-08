"""URL configuration for authentication, profile and user administration."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/password/", views.password_change_view, name="password_change"),
    path("users/", views.user_list, name="user_list"),
    path("users/add/", views.user_create, name="user_add"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/edit/", views.user_update, name="user_edit"),
    path("users/<int:pk>/delete/", views.user_delete, name="user_delete"),
    path("users/<int:pk>/restore/", views.user_restore, name="user_restore"),
]
