from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
import logging

logger = logging.getLogger(__name__)


class ConflictError(Exception):
    """Raised when an action conflicts with existing state (e.g., duplicate membership)."""
    def __init__(self, message="Resource conflict occurred."):
        self.message = message
        super().__init__(self.message)


def custom_exception_handler(exc, context):
    """
    Custom exception handler to standardize all error responses across CollabDocs API:
    - Formats standard DRF exceptions into clean JSON: {"error": ..., "details": ...}
    - Maps Django ObjectDoesNotExist to HTTP 404 NOT FOUND
    - Maps Django IntegrityError / ConflictError to HTTP 409 CONFLICT
    """
    # Call REST framework's default exception handler first to get the standard error response.
    response = exception_handler(exc, context)

    if response is not None:
        # Standardize DRF error response structure
        errors = response.data
        message = "An error occurred while processing your request."
        
        if isinstance(errors, dict):
            if 'detail' in errors:
                message = str(errors['detail'])
            else:
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list) and len(val) > 0:
                    message = f"{first_key}: {val[0]}"
                else:
                    message = f"{first_key}: {val}"
        elif isinstance(errors, list) and len(errors) > 0:
            message = str(errors[0])

        response.data = {
            'success': False,
            'status_code': response.status_code,
            'error': message,
            'details': errors
        }
        return response

    # Handle unhandled Django ObjectDoesNotExist as 404
    if isinstance(exc, ObjectDoesNotExist):
        return Response({
            'success': False,
            'status_code': status.HTTP_404_NOT_FOUND,
            'error': str(exc) or "Requested resource was not found.",
            'details': None
        }, status=status.HTTP_404_NOT_FOUND)

    # Handle unhandled IntegrityError or ConflictError as 409 Conflict
    if isinstance(exc, (IntegrityError, ConflictError)):
        return Response({
            'success': False,
            'status_code': status.HTTP_409_CONFLICT,
            'error': str(exc) or "Integrity error: Database constraint violated or duplicate record.",
            'details': None
        }, status=status.HTTP_409_CONFLICT)

    # Log unexpected internal server errors
    logger.exception("Unhandled server exception encountered in API view:", exc_info=exc)
    return None

