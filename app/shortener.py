import random
import string
from pydantic import HttpUrl, ValidationError

# Base62 alphabet — unambiguous characters only (no 0/O, 1/l/I)
ALPHABET = string.ascii_letters.replace("l", "").replace("I", "").replace("O", "") + \
           string.digits.replace("0", "").replace("1", "")


def generate_code(length: int = 6) -> str:
    """
    Generate a collision-resistant Base62 short code.
    6 chars → ~56B combinations (negligible collision rate up to ~100M links).
    """
    return "".join(random.choices(ALPHABET, k=length))


def validate_url(url) -> None:
    """Raise ValueError for non-HTTP(S) or localhost URLs."""
    s = str(url)
    if not s.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")
    if any(h in s for h in ("localhost", "127.0.0.1", "0.0.0.0", "::1")):
        raise ValueError("Shortening localhost URLs is not allowed")
