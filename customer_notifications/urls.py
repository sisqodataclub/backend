# customer_notifications/urls.py
from django.urls import path
from .views import NotificationCheckView

urlpatterns = [
    path('check/', NotificationCheckView.as_view(), name='notification-check'),
]
