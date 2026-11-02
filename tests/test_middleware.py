from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from collabdocs.middleware import RequestLoggingMiddleware
import io
import sys


class MiddlewareTests(TestCase):
    """
    Section 3.1 & 4.5 Requirement:
    Verifies that RequestLoggingMiddleware measures time in ms and prints log output.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def test_request_logging_middleware_prints_expected_format(self):
        # Dummy get_response returning 200 OK
        def mock_get_response(request):
            return HttpResponse("OK", status=200)

        middleware = RequestLoggingMiddleware(mock_get_response)
        request = self.factory.get('/api/workspaces/')

        # Capture stdout
        captured_output = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = captured_output
            response = middleware(request)
        finally:
            sys.stdout = old_stdout

        self.assertEqual(response.status_code, 200)
        output = captured_output.getvalue()

        # Check required fields printed: HTTP method, Endpoint path, Response status, Time taken
        self.assertIn("Method: GET", output)
        self.assertIn("Path: /api/workspaces/", output)
        self.assertIn("Status: 200", output)
        self.assertIn("Time:", output)
        self.assertIn("ms", output)

