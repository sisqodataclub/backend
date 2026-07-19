from django.db import models
from django.utils import timezone

class NotificationLog(models.Model):
    NOTIFICATION_TYPES = (
        ('arrival', 'Provider Arrival Alert'),
        ('completion', 'Job Completion Notice'),
        ('review', 'Feedback Request'),
    )

    booking_id = models.CharField(max_length=255, db_index=True)
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    recipient_email = models.EmailField()
    sent_at = models.DateTimeField(default=timezone.now)
    is_success = models.BooleanField(default=True)
    error_log = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.notification_type} -> {self.recipient_email} ({'Sent' if self.is_success else 'Failed'})"
