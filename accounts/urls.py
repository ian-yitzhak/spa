from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("signup/verify/", views.verify_email, name="verify_email"),
    path("login/", views.login_view, name="login"),
    path("login/code/", views.login_otp, name="login_otp"),
    path("login/resend/", views.resend_code, name="resend_code"),
    path("logout/", views.UserLogoutView.as_view(), name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/", views.reset_password, name="reset_password"),
    path("account/password/", views.change_password, name="change_password"),
]
