"""The web layer: thin FastAPI routes that pass raw form fields to IOManager and render what it returns."""
import logging
from pathlib import Path
from typing import Callable, Iterable, Iterator, List, Optional, Tuple
import jinja2
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from io_layer.csv_source import CsvSource
from io_layer.form_source import FormSource
from io_layer.io_manager import IOManager
from io_layer.source_error import SourceError
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError

WEB_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024        # the file plus room for typed rows
TOO_LARGE = "The CSV file is larger than 1 MB."
ROW_FIELDS = ("origin_port", "destination_port", "departure_time", "arrival_time")
SEARCH_FIELDS = ("shipment_id", "origin", "destination", "departure_from", "departure_to",
                 "overall_risk", "outcome", "needs_human")

logger = logging.getLogger(__name__)

# main.assess_shipments: (shipments, ai, logic, data) -> (record, save_error) pairs, one per shipment
Runner = Callable[..., Iterable[Tuple[ShipmentRecord, Optional[str]]]]


def create_web_app(io: IOManager, ai, logic, data, demo: bool = False,
                   notices: Optional[List[str]] = None, *, run: Runner) -> FastAPI:
    """Build the FastAPI app. ai and logic may be None while those layers are not connected.

    notices are problems found at startup, such as an unreachable database; every page shows them in red.
    run is the assessment flow (main.assess_shipments), passed in so the web layer never imports main.
    """
    notices = list(notices or [])
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(WEB_DIR / "templates")), autoescape=True)
    templates = Jinja2Templates(env=env)
    app = FastAPI(title="Supply Chain Risk Assessor")
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        context = {"demo": demo, "notices": notices, "form": io.show_input_form(), **context}
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    def input_page(request: Request, rows: list, status_code: int = 200, **context) -> HTMLResponse:
        return page(request, "index.html", status_code, rows=rows or [dict.fromkeys(ROW_FIELDS, "")], **context)

    def render(name: str, **context) -> str:
        return env.get_template(name).render(demo=demo, notices=notices, **context)

    @app.middleware("http")
    async def reject_large_uploads(request: Request, call_next):
        """Refuse an oversized submission from its Content-Length, before the form is read."""
        if request.method == "POST" and request.url.path == "/submit":
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_REQUEST_BYTES:
                html = render("index.html", form=io.show_input_form(), error=TOO_LARGE,
                              rows=[dict.fromkeys(ROW_FIELDS, "")])
                return HTMLResponse(html, status_code=413)
        return await call_next(request)

    def stream_results(shipments: list) -> Iterator[str]:
        """The results page in pieces: the table head, then one row as each shipment finishes, then the end."""
        total = len(shipments)
        done = 0
        yield render("results_start.html", total=total)
        try:
            for record, save_error in run(shipments, ai, logic, data):
                done += 1
                yield render("result_row.html", row=io.show_summary([record])[0], result=io.show_result(record),
                             number=done, total=total, save_error=save_error)
        except Exception:                       # the page has already started, so say so in the table
            logger.exception("Assessment stopped after %d of %d shipments", done, total)
            yield render("result_stopped.html", done=done, total=total)
        yield render("results_end.html", done=done, total=total)

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
                return input_page(request, rows, 413, error=TOO_LARGE)     # sent without a Content-Length
            sources.append(CsvSource(content))
        sources.extend(FormSource(row) for row in rows)
        if not sources:
            return input_page(request, rows, 400, error="Add at least one shipment or choose a CSV file.")
        try:
            preview = io.preview(*sources)
        except SourceError as error:
            return input_page(request, rows, 400, error=str(error))
        except StorageError as error:
            return input_page(request, rows, 503, error=f"{error} Nothing was assessed.")
        if preview.has_problems():
            # Typed rows come after any CSV rows, so typed row i is preview row offset + i.
            offset = preview.total() - len(rows)
            by_number = dict(preview.problems())
            row_errors = [by_number.get(offset + i) for i in range(1, len(rows) + 1)]
            return input_page(request, rows, 422, problems=preview.problems(),
                              row_errors=row_errors, offset=offset)

        shipments = preview.valid_shipments()
        if ai is None or logic is None:
            valid = "1 shipment is valid." if len(shipments) == 1 else f"{len(shipments)} shipments are valid."
            return input_page(request, [], info=f"{valid} AI and Logic are not connected yet.")
        return StreamingResponse(stream_results(shipments), media_type="text/html; charset=utf-8",
                                 headers={"X-Accel-Buffering": "no"})

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request) -> HTMLResponse:
        """The search form and the saved records that match it (all records when no filter is set)."""
        fields = {name: request.query_params.get(name, "") for name in SEARCH_FIELDS}
        return page(request, "search.html", fields=fields, result=io.search(fields))

    return app
