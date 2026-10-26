"""The FastAPI application: the API routes under /api, the built React front (front/dist) everywhere else."""

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from Web.Routes import Auth, Chat, Command, Conversations, Documents, Models, Settings, Status
from Web.Sessions import SessionStore

FRONT_DIR = Path(__file__).resolve().parents[2] / "front" / "dist"
MISSING_FRONT = "Web interface not built: run 'npm install' then 'npm run build' in front/ (or ./install.sh)."
ROUTERS = (Auth, Chat, Command, Conversations, Documents, Models, Settings, Status)


class FrontFiles(StaticFiles):
    """The browser checks every file again (cheap on localhost): an update is never served stale."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(args) -> FastAPI:
    """`args`: the parsed command-line options, used to build each user's Session."""
    app = FastAPI(title="Sensai", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.args = args
    app.state.sessions = SessionStore()
    for module in ROUTERS:
        app.include_router(module.router, prefix="/api")
    if FRONT_DIR.is_dir():
        app.mount("/", FrontFiles(directory=FRONT_DIR, html=True), name="front")
    else:
        app.add_api_route("/", lambda: PlainTextResponse(MISSING_FRONT, status_code=503), include_in_schema=False)
    return app
