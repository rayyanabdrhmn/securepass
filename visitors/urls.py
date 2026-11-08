from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

urlpatterns = [
    path("", views.register, name="register"),
    path("pass/<uuid:token>/", views.visitor_pass, name="visitor_pass"),
    path("pass/<uuid:token>/leave/", views.leave, name="leave"),
    path("pass/<uuid:token>/qr.png", views.pass_qr, name="pass_qr"),
    path("login/", auth_views.LoginView.as_view(template_name="visitors/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("scanner/", views.scanner, name="scanner"),
    path("api/scan/", views.scan_api, name="scan_api"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/dashboard/", views.dashboard_data, name="dashboard_data"),
    path("api/logbook/<int:pk>/exit/", views.mark_exited, name="mark_exited"),
    path("api/logbook/<int:pk>/extend/", views.extend_stay, name="extend_stay"),
    path("api/notifications/<int:pk>/read/", views.dismiss_notification, name="dismiss_notification"),
    path("api/visitors/<int:pk>/blacklist/", views.blacklist_visitor, name="blacklist_visitor"),
    path("api/blacklist/<int:pk>/remove/", views.remove_blacklist, name="remove_blacklist"),
]