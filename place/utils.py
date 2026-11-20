from django.db.models import F, Value, CharField
from django.contrib.gis.geos import Point
from city.models import City

from .models import PlaceKeyword, Place, District, DistrictKeyword


def address_from_places(raw_address, city=None):
    """Places whose keyword occurs in the address; city=None searches every city."""
    places_by_keyword = PlaceKeyword.objects.annotate(querystring=Value(raw_address.lower(), output_field=CharField())) \
        .filter(querystring__icontains=F('place_keyword'))
    if city is not None:
        # Street names repeat between cities.
        places_by_keyword = places_by_keyword.filter(place__city_id=city)

    return places_by_keyword


def district_from_raw(raw_district, place_city=None):
    keywords = DistrictKeyword.objects.annotate(
        querystring=Value(raw_district.lower(), output_field=CharField())
    ).filter(querystring__icontains=F('district_keyword'))

    if place_city:
        keywords = keywords.filter(district__place_city=place_city)

    match = keywords.select_related('district').first()
    return match.district if match else None


def districts_for_coordinates(latitude, longitude, city):
    """Return all matching districts, including boundaries, for one city."""
    if not city or city == City.ALL:
        raise ValueError("A specific city is required")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid coordinates")
    point = Point(longitude, latitude, srid=4326)
    return District.objects.filter(city_id=city, boundary__covers=point)


def place_orm_object(place_id):
    return Place.objects.filter(id=place_id).first()
