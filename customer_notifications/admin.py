from django.contrib import admin
from .models import NotificationLog

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ('booking_id', 'notification_type', 'recipient_email', 'sent_at', 'is_success')
    list_filter = ('notification_type', 'is_success', 'sent_at')
    search_fields = ('booking_id', 'recipient_email', 'error_log')
    readonly_fields = ('booking_id', 'notification_type', 'recipient_email', 'sent_at', 'is_success', 'error_log')
