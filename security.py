"""HTTP security headers shared by the server and the browser test."""
import base64, hashlib, logging, re, sys, traceback
from pathlib import Path


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


def log_failure(context, level=logging.ERROR):
    """Log the current exception's type and stack location, never its message.

    Messages from AdGuard, Nintendo, OIDC or Push libraries can contain URLs, tokens or passwords, so only
    the exception class and file:line frames are written. Call from inside an ``except`` block.
    """
    kind, _, trace = sys.exc_info()
    frames = traceback.extract_tb(trace)[-6:]
    where = ' <- '.join(f'{Path(frame.filename).name}:{frame.lineno} {frame.name}' for frame in reversed(frames))
    logging.log(level, '%s: %s en %s', context, kind.__name__ if kind else 'Error', where or 'ubicación desconocida')
