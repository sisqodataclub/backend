# customer_notifications/emails.py
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .models import NotificationLog
import logging

logger = logging.getLogger(__name__)

# Default ETA – can be overridden in settings.py
DEFAULT_ETA = getattr(settings, 'DEFAULT_ARRIVAL_ETA', 'shortly')


def _compile_and_send(recipient, subject, html_template, text_template, context, booking, notif_type):
    """
    Internal broker to compile template, handle fallbacks, and write to log.
    Now accepts the full `booking` object (any model) for GFK linking.
    """
    if not recipient:
        logger.error(f"Aborted {notif_type}: No recipient email.")
        return False

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@yourdomain.com')

    try:
        html_message = render_to_string(html_template, context)
        plain_message = render_to_string(text_template, context) if text_template else strip_tags(html_message)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[recipient],
            html_message=html_message,
            fail_silently=False,
        )

        # 🚀 Create log using GenericForeignKey – pass the whole object
        NotificationLog.objects.create(
            content_object=booking,       # 👈 Django extracts content_type + object_id automatically
            notification_type=notif_type,
            recipient_email=recipient,
            is_success=True
        )
        return True
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Notification engine failure: {error_msg}")

        NotificationLog.objects.create(
            content_object=booking,       # Even failures are linked to the same booking
            notification_type=notif_type,
            recipient_email=recipient,
            is_success=False,
            error_log=error_msg
        )
        return False


def send_arrival_notification(booking, provider_name=None, eta=None):
    """
    Send arrival notification to customer.

    Args:
        booking: Model instance (e.g., ServiceBooking) with customer_name, customer_email, etc.
        provider_name (str, optional): Override provider name.
        eta (str, optional): Estimated arrival time. Falls back to DEFAULT_ARRIVAL_ETA.
    """
    if eta is None:
        eta = DEFAULT_ETA

    context = {
        'customer_name': getattr(booking, 'customer_name', 'Valued Customer'),
        'provider_name': provider_name or getattr(booking, 'provider_name', 'Our Service Specialist'),
        'eta': eta,
    }

    return _compile_and_send(
        recipient=getattr(booking, 'customer_email', None),
        subject=getattr(settings, 'NOTIF_SUBJECT_ARRIVAL', 'Your provider is on the way!'),
        html_template='customer_notifications/arrival.html',
        text_template='customer_notifications/arrival.txt',
        context=context,
        booking=booking,                 # 👈 Pass the object, not just ID
        notif_type='arrival'
    )


def send_completion_and_review(booking, review_url=None):
    """
    Send completion and review request email.

    Args:
        booking: Model instance with customer_name, customer_email, etc.
        review_url (str, optional): Override review URL. Uses CUSTOMER_REVIEW_URL from settings.
    """
    context = {
        'customer_name': getattr(booking, 'customer_name', 'Valued Customer'),
        'review_url': review_url or getattr(settings, 'CUSTOMER_REVIEW_URL', 'https://g.page/r/your-review-link/review'),
    }

    return _compile_and_send(
        recipient=getattr(booking, 'customer_email', None),
        subject=getattr(settings, 'NOTIF_SUBJECT_REVIEW', 'How was your cleaning experience?'),
        html_template='customer_notifications/review.html',
        text_template='customer_notifications/review.txt',
        context=context,
        booking=booking,                 # 👈 Pass the object
        notif_type='review'
    )
