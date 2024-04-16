from django.core.exceptions import BadRequest
from django.http import HttpRequest, HttpResponse


def detail(_request: HttpRequest, item_id: int) -> HttpResponse:
    return HttpResponse(f'item_id: {item_id}')  # type: ignore


def bad(_request: HttpRequest) -> HttpResponse:
    raise BadRequest('bad request')
