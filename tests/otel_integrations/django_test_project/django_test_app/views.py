from django.core.exceptions import BadRequest
from django.http import HttpResponse


def detail(_request, item_id):
    return HttpResponse(f'item_id: {item_id}')


def bad(_request):
    raise BadRequest('bad request')
