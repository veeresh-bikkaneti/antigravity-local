"""Pure cache key and TTL for one claim. No I/O."""
import hashlib

VERIFIED_TTL = 86400  # a day, for a claim we actually checked
TRANSIENT_TTL = 300  # five minutes, for conflict, unavailable, or anything else


def make_key(claim, context=""):
    """sha256 of the normalised claim plus the context. Context keeps its case."""
    norm_claim = " ".join(claim.lower().strip().rstrip(".").split())
    norm_ctx = " ".join(context.strip().split())
    raw = f"{norm_claim}||{norm_ctx}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def ttl_for(status):
    """86400 only for a verified claim. Everything else expires in five minutes."""
    if status == "verified":
        return VERIFIED_TTL
    return TRANSIENT_TTL
