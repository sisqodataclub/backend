# customer_notifications/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from django.apps import apps
from .models import NotificationLog
import logging

logger = logging.getLogger(__name__)


class NotificationCheckView(APIView):
    """
    Check if a notification (arrival/review) has already been sent for a booking.
    Expects query params: ?booking_id=<id>&type=arrival|review
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        booking_id = request.query_params.get('booking_id')
        notif_type = request.query_params.get('type')  # 'arrival' or 'review'

        if not booking_id or not notif_type:
            return Response(
                {'error': 'booking_id and type are required'},
                status=400
            )

        if notif_type not in ['arrival', 'review']:
            return Response(
                {'error': 'type must be "arrival" or "review"'},
                status=400
            )

        try:
            # Dynamically get the ServiceBooking model to avoid circular import
            ServiceBooking = apps.get_model('services', 'ServiceBooking')
            content_type = ContentType.objects.get_for_model(ServiceBooking)
        except LookupError:
            logger.error('ServiceBooking model not found')
            return Response(
                {'error': 'ServiceBooking model not found'},
                status=500
            )

        # Check if a successful notification of this type exists for this booking
        sent = NotificationLog.objects.filter(
            content_type=content_type,
            object_id=booking_id,
            notification_type=notif_type,
            is_success=True
        ).exists()

        return Response({'sent': sent})
