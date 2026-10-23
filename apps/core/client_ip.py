def get_client_ip(request):
    """
    Returns the real client IP for rate limiting.

    WHY SECURE: In production every request passes through nginx, which resolves the
    visitor IP from Cloudflare's CF-Connecting-IP (trusted only from the docker network)
    and always overwrites X-Real-IP, so the header cannot be spoofed by clients.
    Falls back to REMOTE_ADDR for direct requests (local dev, internal health checks).
    """
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', '')
