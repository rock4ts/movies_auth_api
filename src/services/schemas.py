from typing import Mapping

from pydantic import BaseModel, HttpUrl


class HttpRequestComponents(BaseModel):
    url: HttpUrl
    params: Mapping | None = None
    data: Mapping | None = None
    headers: dict | None = None
