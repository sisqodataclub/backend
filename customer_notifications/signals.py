from .emails import send_arrival_notification, send_completion_and_review

def generic_arrival_handler(sender, instance, **kwargs):
    if getattr(instance, 'status', None) == 'in_progress':
        send_arrival_notification(instance)

def generic_completion_handler(sender, instance, **kwargs):
    if getattr(instance, 'status', None) == 'completed':
        send_completion_and_review(instance)

def connect_notification_triggers(model_class):
    from django.db.models.signals import post_save
    post_save.connect(generic_arrival_handler, sender=model_class)
    post_save.connect(generic_completion_handler, sender=model_class)
