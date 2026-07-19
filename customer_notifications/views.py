# customer_notifications/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import NotificationLog

class NotificationCheckView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        booking_id = request.query_params.get('booking_id')
        notif_type = request.query_params.get('type')  # 'arrival' or 'review'

        if not booking_id or not notif_type:
            return Response({'error': 'booking_id and type are required'}, status=400)

        sent = NotificationLog.objects.filter(
            booking_id=str(booking_id),
            notification_type=notif_type,
            is_success=True
        ).exists()

        return Response({'sent': sent})
