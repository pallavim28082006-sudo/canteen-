"""QR code generation."""
import io

import qrcode


def make_qr(data):
    """Return PNG bytes for the given text."""
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
