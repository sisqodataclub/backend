from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from .emails import send_arrival_notification, send_completion_and_review

class NotificationButtonsMixin:
    @action(detail=True, methods=['post'])
    def notify_arrival(self, request, pk=None):
        booking = self.get_object()
        if send_arrival_notification(booking):
            return Response({"message": "Arrival email sent."}, status=status.HTTP_200_OK)
        return Response({"error": "Failed to send."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'])
    def request_review(self, request, pk=None):
        booking = self.get_object()
        if send_completion_and_review(booking):
            return Response({"message": "Review request sent."}, status=status.HTTP_200_OK)
        return Response({"error": "Failed to send."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
