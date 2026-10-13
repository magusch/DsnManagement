from urllib.parse import urlsplit

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .context import SESSION_KEY
from .models import get_cities


@staff_member_required
@require_POST
def switch_city(request):
    code = request.POST.get('city')
    if code in get_cities():
        request.session[SESSION_KEY] = code

    # Back to the same page but without its query: filters (place, category, …)
    # usually point at rows of the previous city.
    referer = request.META.get('HTTP_REFERER', '')
    if referer and url_has_allowed_host_and_scheme(referer, {request.get_host()}, request.is_secure()):
        return redirect(urlsplit(referer).path)
    return redirect('admin:index')
