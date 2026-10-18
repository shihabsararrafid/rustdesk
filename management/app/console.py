from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()
STATIC = Path(__file__).resolve().parents[1] / 'static'
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"


@router.get('/console', include_in_schema=False)
def console():
    return FileResponse(STATIC / 'index.html', headers={'Content-Security-Policy': CSP})


@router.get('/console/assets/{asset:path}', include_in_schema=False)
def asset(asset: str):
    allowed = {'console.js', 'console.css', 'vendor/lucide.js'}
    if asset not in allowed:
        raise HTTPException(404, 'Asset not found')
    return FileResponse(STATIC / asset, headers={'Content-Security-Policy': CSP})
