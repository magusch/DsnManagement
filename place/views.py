import json

# from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
# from django.shortcuts import redirect
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from city.context import city_from_request
from city.models import City

from .models import Place

from django.template import loader

from . import utils

#@staff_member_required
def place_address(request):
    raw_address = None
    if request.method == "GET":
        if 'address' in request.GET:
            raw_address = request.GET['address']
    elif request.method == "POST":
        raw_address = request.POST['address']

    address = {"raw_address": raw_address}

    if raw_address:
        place_by_keywords = utils.address_from_places(raw_address, city_from_request(request))
        if place_by_keywords:
            place = place_by_keywords[0]
            address.update({
                "response_code": 200,
                "address": place.place.place_name,
                "address_for_post": f"{place.place.markdown_address()}"
            })
        else:
            address.update({
                "response_code": 402,
                })
    else:
        address.update({
            "response_code": 400
        })

    return HttpResponse(json.dumps(address))


@staff_member_required
def find_place(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if is_ajax:
        if request.method == 'GET':
            place_name = request.GET.get('query', '')
            places = list()
            places_qs = Place.objects.filter(place_name__icontains=place_name)
            if request.city != City.ALL:
                places_qs = places_qs.filter(city_id=request.city)
            for place in places_qs:
                places.append({
                    'id': place.id,
                    'place_name': place.place_name,
                    'address': place.place_address,
                    'metro': place.place_metro,
                })
            return JsonResponse({'results': places})
        return JsonResponse({'status': 'Invalid request'}, status=400)
    else:
        return HttpResponseBadRequest('Invalid request')


def all_places(request):
    all_places = Place.objects.all()
    template = loader.get_template('all_places.html')
    context = {
        'all_places': all_places,
    }
    return HttpResponse(template.render(context, request))