"""The web layer: thin FastAPI routes that pass raw form fields to IOManager and render what it returns."""
from pathlib import Path
from typing import List, Optional
import jinja2
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from io_layer.csv_source import CsvSource
from io_layer.form_source import FormSource
from io_layer.io_manager import IOManager
from io_layer.source_error import SourceError

WEB_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 1024 * 1024
ROW_FIELDS = ("origin_port", "destination_port", "departure_time", "arrival_time")


def create_web_app(io: IOManager, ai, logic, data, demo: bool = False) -> FastAPI:
    """Build the FastAPI app. ai and logic may be None while those layers are not connected."""
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(WEB_DIR / "templates")), autoescape=True)
    templates = Jinja2Templates(env=env)
    app = FastAPI(title="Supply Chain Risk Assessor")
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        context = {"demo": demo, "form": io.show_input_form(), **context}
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    def input_page(request: Request, rows: list, status_code: int = 200, **context) -> HTMLResponse:
        return page(request, "index.html", status_code, rows=rows or [dict.fromkeys(ROW_FIELDS, "")], **context)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        """The input page: a table of typed rows and a CSV upload."""
        return input_page(request, [])

    @app.post("/submit", response_class=HTMLResponse)
    def submit(request: Request,
               origin_port: List[str] = Form(default=[]),
               destination_port: List[str] = Form(default=[]),
               departure_time: List[str] = Form(default=[]),
               arrival_time: List[str] = Form(default=[]),
               csv_file: Optional[UploadFile] = File(default=None)) -> HTMLResponse:
        """Validate every row. If all are valid, assess them; otherwise show every error and run nothing."""
        typed = {"origin_port": origin_port, "destination_port": destination_port,
                 "departure_time": departure_time, "arrival_time": arrival_time}
        rows = [source.read()[0] for source in FormSource.many(typed)]
        sources = []
        if csv_file is not None and csv_file.filename:
            content = csv_file.file.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                return input_page(request, rows, 413, error="The CSV file is larger than 1 MB.")
            sources.append(CsvSource(content))
        sources.extend(FormSource(row) for row in rows)
        if not sources:
            return input_page(request, rows, 400, error="Add at least one shipment or choose a CSV file.")
        try:
            preview = io.preview(*sources)
        except SourceError as error:
            return input_page(request, rows, 400, error=str(error))
        if preview.has_problems():
            return input_page(request, rows, 422, problems=preview.problems())

        count = len(preview.valid_shipments())
        valid = "1 shipment is valid." if count == 1 else f"{count} shipments are valid."
        return input_page(request, [], info=f"{valid} AI and Logic are not connected yet.")

    return app
