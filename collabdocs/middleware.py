import time
import logging

logger = logging.getLogger('collabdocs.middleware')


class RequestLoggingMiddleware:
    """
    Custom Request Logging Middleware for CollabDocs.
    
    Requirement:
    - Measures time taken for every incoming HTTP request.
    - Prints HTTP method, endpoint path, response status code, and execution time in ms.
    - Registered in settings.py MIDDLEWARE list.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Record start timestamp
        start_time = time.perf_counter()

        # 2. Process request through view and subsequent middlewares
        response = self.get_response(request)

        # 3. Compute elapsed time in milliseconds
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # 4. Format log message as requested in Section 3.1
        log_message = (
            f"[CollabDocs Logger] Method: {request.method} | "
            f"Path: {request.path} | "
            f"Status: {response.status_code} | "
            f"Time: {duration_ms:.2f}ms"
        )

        # 5. Output to standard stdout via print and standard logging
        print(log_message)
        logger.info(log_message)

        return response

