import datetime

from pyramid.events import subscriber
from pyramid.events import NewResponse
from pyramid.response import FileResponse
from pyramid.security import authenticated_userid

CACHE_POLICY_HEADER = 'x-caching-policy'


def set_max_age(response, delta, cache_ctrl=None):
    """Sets max-age and expires headers based on the timedelta `delta`.

    If `cache_ctrl` is not None, I'll add items found therein to the
    Cache-Control header.

    Will overwrite existing values and preserve non overwritten ones.
    """
    if cache_ctrl is None:
        cache_ctrl = {}

    seconds = delta.seconds + delta.days * 24 * 60 * 60
    if seconds < 0:
        seconds = 0
    now = datetime.datetime.utcnow()

    cache_ctrl.setdefault('max-age', seconds)

    # Preserve an existing cache-control header:
    existing = response.headers.get('cache-control')
    if existing:
        for e in [e.strip() for e in existing.split(',')]:
            kv = e.split('=')
            if len(kv) == 2:
                cache_ctrl.setdefault(kv[0], kv[1])
            else:
                cache_ctrl.setdefault(kv[0], None)

    # Render the cache-control header:
    cache_control_header = []
    for key, value in sorted(cache_ctrl.items()):
        if value is None:
            cache_control_header.append(key)
        else:
            cache_control_header.append('%s=%s' % (key, value))
    cache_control_header = ','.join(cache_control_header)
    response.headers['cache-control'] = cache_control_header

    response.headers['expires'] = (now + delta).strftime(
        "%a, %d %b %Y %H:%M:%S GMT")


# This is our mapping of caching policies (X-Caching-Policy) to
# functions that set the response headers accordingly:
caching_policies = {
    'Cache HTML':
    lambda response: set_max_age(response, datetime.timedelta(days=-1),
                                  cache_ctrl={'s-maxage': '3600'}),

    'Cache Media Content':
    lambda response: set_max_age(response, datetime.timedelta(hours=4)),

    'Cache Resource':
    lambda response: set_max_age(response, datetime.timedelta(days=32),
                                  cache_ctrl={'public': None}),

    'No Cache':
    lambda response: set_max_age(response, datetime.timedelta(days=-1)),
}


def choose_caching_policy(context, request, response):
    authenticated = authenticated_userid(request) is not None
    if request.method != 'GET':
        return 'No Cache'
    elif isinstance(response, FileResponse):
        return 'Cache Resource'
    elif authenticated:
        return 'No Cache'
    elif response.headers['content-type'].startswith('text/html'):
        return 'Cache HTML'
    else:
        return 'Cache Media Content'


@subscriber(NewResponse)
def set_cache_headers(event):
    request, response = event.request, event.response
    context = event.request.context

    # If no caching policy was previously set (by setting the
    # CACHE_POLICY_HEADER header), we'll choose one at this point:
    caching_policy = response.headers.get(CACHE_POLICY_HEADER)
    if caching_policy is None:
        caching_policy = choose_caching_policy(context, request, response)
    if caching_policy is not None:
        response.headers[CACHE_POLICY_HEADER] = caching_policy

    # And here we'll set the headers for the caching policy:
    if caching_policy:
        caching_policies[caching_policy](response)


def includeme(config):
    config.scan('kotti.views.cache')