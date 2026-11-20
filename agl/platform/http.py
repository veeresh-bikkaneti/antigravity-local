"""The one HTTP helper: a single JSON entry point with a required timeout, one private place that
opens a request, and the same-host redirect opener. The Layer contract in docs/ARCHITECTURE.md
puts HTTP here; the timeout is a keyword-only argument with no default so every caller keeps
its own current default at the call site."""
import http.client
import json
import urllib.error
import urllib.request


class _SameHostOnly(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when it stays on the host we asked. Anything else is an error, not a new host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit
        if urlsplit(newurl).netloc != urlsplit(req.full_url).netloc:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def same_host_opener():
    """An opener that follows a redirect only while it stays on the host we asked."""
    return urllib.request.build_opener(_SameHostOnly)


def _urlopen(request, timeout):
    """urllib.request.urlopen by its current module attribute, so a test that patches it still applies."""
    return urllib.request.urlopen(request, timeout=timeout)


# Error groups a caller may classify without importing the banned modules itself.
ANSWERED_ERRORS = (urllib.error.HTTPError, http.client.HTTPException)  # the server answered: 404, a cut-off reply
NETWORK_ERRORS = (urllib.error.URLError, OSError, TimeoutError)       # nothing answered: refused, down, timeout


def _open(url, *, timeout, method=None, headers=None, data=None, opener=None):
    """The one place a request is opened. A plain GET (no data, method, headers or opener) keeps urlopen's
    exact old call shape, a bare url, so a test or caller that watches urlopen sees what it saw before; the
    Request is built only when data, method, headers or an opener need it. `opener` is None (urllib.request.urlopen),
    a urlopen-style callable, or an opener with .open. HTTP errors raise through; the caller decides what they mean."""
    if opener is None and data is None and method is None and not headers:
        return _urlopen(url, timeout=timeout)
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if opener is None:
        return _urlopen(request, timeout=timeout)
    if callable(opener):
        return opener(request, timeout=timeout)
    return opener.open(request, timeout=timeout)


def get_json(url, *, timeout, headers=None, data=None, opener=None):
    """The parsed JSON of the reply. `timeout` has no default on purpose: the caller passes its own.
    `data` is a POST body (a GET when it is None); `opener` as in _open."""
    with _open(url, timeout=timeout, headers=headers, data=data, opener=opener) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_text(url, timeout):
    """Body text of a 200 reply, or None for anything else (refused, timeout, non-200)."""
    try:
        with _open(url, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8")
    except Exception:
        pass
    return None
