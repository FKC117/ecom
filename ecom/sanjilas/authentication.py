"""Shared lockout response for React and Django admin authentication."""
from django.http import HttpResponse
from django.utils.html import escape


def lockout_response(request, response=None, credentials=None):
    from .control import api_error, labels
    if request.path.startswith('/api/'):
        result = api_error('login_limited', 429)
    else:
        result = HttpResponse(escape(labels()['login_limited']), status=429)
    result['Retry-After'] = '900'
    result['Cache-Control'] = 'no-store'
    return result
