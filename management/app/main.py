import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import auth, audit, directory, employees, policies, console, recordings
from .database import connect_database, migrate
from .settings import Settings


class BodyLimit:
    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        # Bound the full stream, including chunked requests without Content-Length.
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > self.maximum:
                return await JSONResponse({'error': 'Request too large'}, 413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(settings=None):
    settings = settings or Settings.from_env()
    migrate(settings.database_path)
    app = FastAPI(title='Sasthotech Management API', version='0.1.0')
    app.state.settings = settings
    app.add_middleware(BodyLimit, maximum=settings.max_body_bytes)

    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(request: Request, exc):
        return JSONResponse({'error': 'Duplicate or referenced record'}, status_code=409)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_unavailable(request: Request, exc):
        return JSONResponse({'error': 'Database unavailable'}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        # Pydantic errors can echo the supplied password or authorization payload.
        return JSONResponse({'error': 'Invalid request fields'}, status_code=422)

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc):
        return JSONResponse({'error': exc.detail}, status_code=exc.status_code, headers=exc.headers)

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.get('/healthz')
    def health():
        return {'status': 'ok'}

    @app.get('/readyz')
    def ready():
        with connect_database(settings.database_path) as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ready'}

    for router in (auth.router, employees.router, directory.router, audit.router, policies.router, console.router, recordings.router):
        app.include_router(router)
    return app
