from typing import Dict, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


class CustomHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: Union[dict, str]):
        super().__init__(
            status_code=status_code,
            detail=detail,
            headers={"Content-Type": "application/json"},
        )
