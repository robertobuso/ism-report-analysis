"""Minimal HTTP server for Railway healthchecks (Celery worker)."""
from http.server import HTTPServer, BaseHTTPRequestHandler


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Respond to all GET requests with 200 OK."""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Celery Worker: OK')

    def log_message(self, format, *args):
        """Suppress access logs."""
        pass


if __name__ == "__main__":
    port = 8000
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"Health check server listening on port {port}")
    server.serve_forever()
