"""Reference plugin — auto-mounted at /plugins/example_echo/*"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
async def ping():
    return {"plugin": "example_echo", "ok": True}


@router.post("/echo")
async def echo(payload: dict):
    return {"plugin": "example_echo", "received": payload}
