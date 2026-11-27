"""Check a batch of claims through the cache, at most three searches, and one local completion."""
import json

from agl.core.verification_prompts import VERIFIER_SYSTEM_PROMPT

UNAVAILABLE = "Data not available."
_MAX_SEARCHES = 3


def unavailable(claim):
    """A miss we could not check. conf is none so the main agent drops it."""
    return {
        "claim": claim,
        "status": "unavailable",
        "conf": "none",
        "extract": UNAVAILABLE,
        "sources": [],
    }


def run_verifier_subagent(claims, context, *, ports):
    """One result per input claim, in that order. Cache hits are not checked again."""
    store, owned = _open_cache(ports)
    try:
        if store is None:
            return [unavailable(claim) for claim in claims]
        found, misses = store.get_many(claims, context)
        fresh = _resolve_misses(ports, store, misses, context) if misses else {}
        return _in_order(claims, found, fresh)
    finally:
        if owned is not None:
            owned.close()


def _open_cache(ports):
    """(store, owned). The caller closes owned. owned is None when the store was injected."""
    store = ports.claim_store
    if store is not None:
        return store, None
    opener = getattr(ports, "open_claim_store", None)
    if opener is None:
        return None, None
    opened = opener()
    return opened, opened


def bind_verify_claims(ports):
    """A tool closure named verify_claims. The SDK reads that __name__."""

    def verify_claims(claims, provided_context=""):
        """Check atomic factual claims. provided_context is optional text to read first."""
        rows = run_verifier_subagent(claims, provided_context, ports=ports)
        return json.dumps({"results": rows}, separators=(",", ":"), ensure_ascii=True)

    return verify_claims


def _in_order(claims, found, fresh):
    rows = []
    for claim in claims:
        if claim in found:
            rows.append(found[claim])
        else:
            rows.append(fresh[claim])
    return rows


def _resolve_misses(ports, store, misses, context):
    packets = _search_some(ports, misses)
    if packets is None:
        return _store_rows(store, [unavailable(claim) for claim in misses], context)
    raw = ports.complete(system=VERIFIER_SYSTEM_PROMPT, user=_user_text(misses, packets, context))
    rows = _rows_for(misses, _parse_results(raw))
    return _store_rows(store, rows, context)


def _store_rows(store, rows, context):
    store.set_many(rows, context)
    return {row["claim"]: row for row in rows}


def _search_some(ports, misses):
    """Up to three searches. None means there is no backend, so do not complete."""
    if ports.web_search is None:
        return None
    packets = []
    for claim in list(misses)[:_MAX_SEARCHES]:
        packet = _ask(ports, claim)
        if packet is None:
            return None
        packets.append(packet)
    return packets


def _ask(ports, claim):
    try:
        result = ports.web_search.search(claim, http=ports.http, env=_env(ports))
    except Exception:
        return None
    if not isinstance(result, dict) or result.get("backend") in (None, "none"):
        return None
    return {"claim": claim, "hits": _clean_hits(result.get("hits"))}


def _env(ports):
    env = getattr(ports, "env", None)
    if env is not None:
        return env
    return ports.os.environ


def _clean_hits(hits):
    if not isinstance(hits, list):
        return []
    clean = []
    for hit in hits:
        if isinstance(hit, dict):
            url = hit.get("url")
            snippet = hit.get("snippet")
            clean.append({
                "url": url if isinstance(url, str) else "",
                "snippet": snippet if isinstance(snippet, str) else "",
            })
    return clean


def _user_text(misses, packets, context):
    body = {"claims": list(misses), "sources": packets}
    if context:
        body["context"] = context
    return json.dumps(body, separators=(",", ":"), ensure_ascii=True)


def _parse_results(raw):
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    return None


def _rows_for(misses, parsed):
    if parsed is None:
        return [unavailable(claim) for claim in misses]
    by_claim = {}
    for row in parsed:
        if isinstance(row, dict) and isinstance(row.get("claim"), str) and "status" in row:
            by_claim.setdefault(row["claim"], row)
    return [by_claim.get(claim) or unavailable(claim) for claim in misses]
