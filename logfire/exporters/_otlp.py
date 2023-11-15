from __future__ import annotations

from typing import Any, Iterable, cast

from requests import Session
from requests.models import PreparedRequest, Response


class OTLPExporterHttpSession(Session):
    def __init__(self, *args: Any, max_body_size: int | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.max_body_size = max_body_size

    def send(self, request: PreparedRequest, **kwargs: Any) -> Response:
        if request.body is not None and self.max_body_size is not None:
            if isinstance(request.body, (str, bytes)):  # type: ignore
                if len(request.body) > self.max_body_size:
                    raise ValueError(
                        f'Request body is too large ({len(request.body)} bytes), '
                        f'must be less than {self.max_body_size} bytes.'
                    )
            else:
                # assume a generator
                body = cast('Iterable[bytes]', request.body)

                def gen(max_body_size: int = self.max_body_size) -> Iterable[bytes]:
                    total = 0
                    for chunk in body:
                        total += len(chunk)
                        if total > max_body_size:
                            raise ValueError(
                                f'Request body is too large ({total} bytes), '
                                f'must be less than {self.max_body_size} bytes.'
                            )
                        yield chunk

                request.body = gen()  # type: ignore
        return super().send(request, **kwargs)
