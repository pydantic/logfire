from django.core.exceptions import BadRequest
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI
from ninja.errors import HttpError

ninja_api = NinjaAPI(urls_namespace='ninja')


def detail(_request: HttpRequest, item_id: int) -> HttpResponse:
    return HttpResponse(f'item_id: {item_id}')  # type: ignore


def bad(_request: HttpRequest) -> HttpResponse:
    raise BadRequest('bad request')


@ninja_api.get('/good/')
def ninja_good(request: HttpRequest) -> dict[str, str]:
    return {'message': 'ok'}


@ninja_api.get('/error/')
def ninja_error(request: HttpRequest) -> dict[str, str]:
    raise HttpError(400, 'ninja error')


@ninja_api.get('/unhandled/')
def ninja_unhandled(request: HttpRequest) -> dict[str, str]:
    raise RuntimeError('unhandled ninja error')
