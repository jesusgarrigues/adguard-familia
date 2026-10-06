"""HTTP security headers shared by the server and the browser test."""
import base64, hashlib, re


def content_security_policy(page):
    """Strict CSP: same-origin code plus the hash of each inline <script> actually served in index.html.

    Styles keep 'unsafe-inline' because the page has a <style> block and sets styles from scripts; injected
    styles cannot run code. HSTS is left to the HTTPS proxy, since LAN installations may use plain HTTP.
    """
    hashes = ["'sha256-" + base64.b64encode(hashlib.sha256(code.encode()).digest()).decode() + "'"
              for code in re.findall(r'<script>(.*?)</script>', page, re.S)]
    return '; '.join((
        "default-src 'self'",
        "script-src 'self' " + ' '.join(hashes),
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ))
