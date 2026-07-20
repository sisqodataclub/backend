# customer_notifications/admin.py
from django.contrib import admin
from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'content_type',
        'object_id',
        'related_object_display',
        'notification_type',
        'recipient_email',
        'sent_at',
        'is_success',
    )
    list_filter = ('notification_type', 'is_success', 'sent_at')
    search_fields = ('object_id', 'recipient_email', 'error_log')
    readonly_fields = (
        'content_type',
        'object_id',
        'related_object_display',
        'sent_at',
        'notification_type',
        'recipient_email',
        'is_success',
        'error_log',
    )
    fieldsets = (
        ('Notification Details', {
            'fields': ('notification_type', 'recipient_email', 'sent_at', 'is_success')
        }),
        ('Related Object (Generic FK)', {
            'fields': ('content_type', 'object_id', 'related_object_display')
        }),
        ('Error Information', {
            'fields': ('error_log',),
            'classes': ('collapse',)
        }),
    )

    def related_object_display(self, obj):
        """Return a string representation of the related object."""
        if obj.content_object:
            return str(obj.content_object)
        return "—"
    related_object_display.short_description = "Related Object"
