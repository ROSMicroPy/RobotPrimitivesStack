
# This copyright notice must be included 
# in all distributions of this code
#
# Copyright (c) 2026 John Gentilin
# Author: John Gentilin
# All rights reserved unless otherwise stated.
#
#
from .propagation import inject_traceparent


# Wrap an HTTP request in a span and propagate trace identity through its headers.
def traced_request(tracer, method, url, headers=None, data=None, timeout_s=5):
    req_headers = dict(headers or {})
    with tracer.start_as_current_span("HTTP {}".format(method.upper())) as span:
        span.set_attribute("http.method", method.upper())
        span.set_attribute("http.url", url)
        inject_traceparent(req_headers, span=span)

        try:
            import urequests as requests  # type: ignore

            response = requests.request(
                method=method,
                url=url,
                data=data,
                headers=req_headers,
                timeout=timeout_s,
            )
            span.set_attribute("http.status_code", getattr(response, "status_code", 0))
            return response
        except ImportError:
            from urllib import request

            req = request.Request(
                url=url,
                data=(data.encode("utf-8") if isinstance(data, str) else data),
                headers=req_headers,
                method=method.upper(),
            )
            response = request.urlopen(req, timeout=timeout_s)
            span.set_attribute("http.status_code", response.getcode())
            return response
        except Exception as exc:
            span.record_exception(exc)
            raise
