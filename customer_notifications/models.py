from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

class NotificationLog(models.Model):
    NOTIFICATION_TYPES = (
        ('arrival', 'Provider Arrival Alert'),
        ('completion', 'Job Completion Notice'),
        ('review', 'Feedback Request'),
    )

    # --- Generic Foreign Key (the magic bridge) ---
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # --- Notification fields ---
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    recipient_email = models.EmailField()
    sent_at = models.DateTimeField(default=timezone.now)
    is_success = models.BooleanField(default=True)
    error_log = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.notification_type} -> {self.recipient_email} ({'Sent' if self.is_success else 'Failed'})"
