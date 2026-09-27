import os

from rest_framework.permissions import BasePermission


class HasAgentApiKey(BasePermission):
    """
    Allow access only when the request carries the correct agent API key
    in the ``X-Agent-Key`` header.

    The expected key is read from the ``AGENT_API_KEY`` environment variable.
    If the env var is unset or the header is missing/wrong, access is denied.
    """

    message = "Invalid or missing agent API key."

    def has_permission(self, request, view):
        expected = os.environ.get('AGENT_API_KEY')
        provided = request.headers.get('X-Agent-Key')
        return bool(expected) and provided == expected
