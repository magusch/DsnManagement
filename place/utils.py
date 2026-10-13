from django.db.models import F, Value, CharField

from .models import PlaceKeyword, Place, DistrictKeyword


def address_from_places(raw_address):
    places_by_keyword = PlaceKeyword.objects.annotate(querystring=Value(raw_address.lower(), output_field=CharField())) \
        .filter(querystring__icontains=F('place_keyword'))

    return places_by_keyword


def district_from_raw(raw_district, place_city=None):
    keywords = DistrictKeyword.objects.annotate(
        querystring=Value(raw_district.lower(), output_field=CharField())
    ).filter(querystring__icontains=F('district_keyword'))

    if place_city:
        keywords = keywords.filter(district__place_city=place_city)

    match = keywords.select_related('district').first()
    return match.district if match else None


def place_orm_object(place_id):
    return Place.objects.filter(id=place_id).first()
