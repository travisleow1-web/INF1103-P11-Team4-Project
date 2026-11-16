"""The web layer: thin FastAPI routes that pass raw form fields to IOManager and render what it returns."""
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
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
from web.status_feed import StatusFeed

WEB_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024        # the file plus room for typed rows
TOO_LARGE = "The CSV file is larger than 1 MB."
NO_AI = "AI is not connected: set GEMINI_API_KEY in .env (or start with DEMO_MODE=1)."
NO_LOGIC = "Logic is not connected yet."
NO_AI_OR_LOGIC = "AI and Logic are not connected yet."
ROW_FIELDS = ("origin_port", "destination_port", "departure_time", "arrival_time")
RULE_FIELDS = {
    "confidence_min":            ("Minimum AI confidence (0 to 1)", "0.01", "0", "1"),
    "history_window_days":       ("Route history window (days)", "1", "1", ""),
    "perfect_storm_min_mediums": ("Medium-or-worse factors for a Perfect Storm", "1", "1", "3"),
    "data_max_age_hours":        ("Oldest usable external data (hours)", "1", "1", ""),
    "delay_days_limit":          ("Delay that raises risk to Medium (days)", "1", "1", ""),
    "delay_days_high":           ("Delay that raises risk to High (days)", "1", "1", ""),
}
SEARCH_FIELDS = ("shipment_id", "origin", "destination", "departure_from", "departure_to",
                 "overall_risk", "outcome", "needs_human")

logger = logging.getLogger(__name__)

# main.assess_shipments: (shipments, ai, logic, data) -> (record, save_error) pairs, one per shipment
Runner = Callable[..., Iterable[Tuple[ShipmentRecord, Optional[str]]]]


def static_url(name: str) -> str:
    """Link to a file in web/static with its change time, so a browser never shows an old copy after an update."""
    return f"/static/{name}?v={int((WEB_DIR / 'static' / name).stat().st_mtime)}"


def not_connected_message(ai, logic) -> Optional[str]:
    """What to tell users when the AI or Logic layer is missing, or None when both are connected."""
    if ai is None and logic is None:
        return NO_AI_OR_LOGIC
    if ai is None:
        return NO_AI
    if logic is None:
        return NO_LOGIC
    return None


def create_web_app(io: IOManager, ai, logic, data, demo: bool = False,
                   notices: Optional[List[str]] = None, *, run: Runner) -> FastAPI:
    """Build the FastAPI app. ai and logic may be None while those layers are not connected.

    notices are problems found at startup, such as an unreachable database; every page shows them in red.
    run is the assessment flow (main.assess_shipments), passed in so the web layer never imports main.
    """
    notices = list(notices or [])
    not_connected = not_connected_message(ai, logic)
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(WEB_DIR / "templates")), autoescape=True)
    env.globals["static_url"] = static_url
    templates = Jinja2Templates(env=env)
    app = FastAPI(title="Supply Chain Risk Assessor")
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def page(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
        context = {"demo": demo, "notices": notices, "not_connected": not_connected, "form": io.show_input_form(),
                   **context}
        return templates.TemplateResponse(request, name, context, status_code=status_code)

    def input_page(request: Request, rows: list, status_code: int = 200, **context) -> HTMLResponse:
        return page(request, "index.html", status_code, rows=rows or [dict.fromkeys(ROW_FIELDS, "")], **context)

    def render(name: str, **context) -> str:
        return env.get_template(name).render(demo=demo, notices=notices, not_connected=not_connected, **context)

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

    def stream_results(shipments: list, replace: bool = False, skipped: Optional[List[str]] = None) -> Iterator[str]:
        """The results page in pieces: the table head, then one row as each shipment finishes, then the end.

        replace=True is a re-run: each result overwrites the saved record. skipped are IDs that were not re-run.
        """
        total = len(shipments)
        position = {shipment.shipment_id: number for number, shipment in enumerate(shipments, 1)}
        done = 0
        finished = []
        not_saved = 0
        started = time.monotonic()
        updates: Queue = Queue()                # finished rows and AI status lines, in the order they happen
        feed = StatusFeed(position, updates)
        stop = threading.Event()

        def assess() -> None:
            """Assess in another thread, so the page can show what the AI is doing while it works."""
            try:
                for item in run(shipments, ai, logic, data, replace=replace):
                    updates.put(("row", item))
                    if stop.is_set():           # the browser went away: start no more shipments
                        break
            except Exception as error:
                updates.put(("error", error))
            updates.put(("end", None))

        yield render("results_start.html", total=total, rerun=replace, skipped=skipped or [])
        ai.add_listener(feed)
        threading.Thread(target=assess, daemon=True).start()
        try:
            while True:
                kind, payload = updates.get()
                if kind == "status":
                    text = f"Assessing {payload.shipment_id} ({position[payload.shipment_id]} of {total}) - AI: {payload.describe()}"
                    yield render("status.html", text=text)
                elif kind == "row":
                    record, save_error = payload
                    done += 1
                    finished.append(record)
                    not_saved += 1 if save_error else 0
                    suggestion = io.show_reschedule([record])
                    yield render("result_row.html", row=io.show_summary([record])[0], result=io.show_result(record),
                                 number=done, total=total, save_error=save_error,
                                 reschedule=suggestion[0] if suggestion else None)
                elif kind == "error":           # the page has already started, so say so in the table
                    logger.error("Assessment stopped after %d of %d shipments", done, total, exc_info=payload)
                    yield render("result_stopped.html", done=done, total=total)
                else:
                    break
        finally:
            stop.set()
            ai.remove_listener(feed)
        yield render("status.html", text="")
        report = io.show_report(finished, not_saved=not_saved, planned=total, seconds=time.monotonic() - started,
                                finished_at=datetime.now(timezone.utc))
        yield render("results_end.html", done=done, total=total, report=report)

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
        typed_sources = FormSource.many(typed)
        rows = [source.read()[0] for source in typed_sources]            # to fill the form again
        sources = []
        if csv_file is not None and csv_file.filename:
            content = csv_file.file.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                return input_page(request, rows, 413, error=TOO_LARGE)     # sent without a Content-Length
            sources.append(CsvSource(content))
        sources.extend(typed_sources)
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
        if not_connected:
            valid = "1 shipment is valid." if len(shipments) == 1 else f"{len(shipments)} shipments are valid."
            return input_page(request, rows, info=f"{valid} {not_connected}")
        return StreamingResponse(stream_results(shipments), media_type="text/html; charset=utf-8",
                                 headers={"X-Accel-Buffering": "no"})

    @app.post("/rerun", response_class=HTMLResponse)
    def rerun(request: Request, shipment_id: List[str] = Form(default=[])) -> HTMLResponse:
        """Assess again the saved shipments the AI could not assess; each new record replaces the old one."""
        if not_connected:
            return input_page(request, [], 503, error=f"{not_connected} Nothing was re-run.")
        if not any(text.strip() for text in shipment_id):
            return input_page(request, [], 400, error="Choose at least one shipment to re-run.")
        try:
            shipments, skipped = io.shipments_to_rerun(shipment_id)
        except StorageError as error:
            return input_page(request, [], 503, error=f"{error} Nothing was re-run.")
        if not shipments:
            return input_page(request, [], 400, error="Nothing was re-run: those shipments are not saved or "
                                                      "already have an AI assessment.")
        return StreamingResponse(stream_results(shipments, replace=True, skipped=skipped),
                                 media_type="text/html; charset=utf-8", headers={"X-Accel-Buffering": "no"})

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request) -> HTMLResponse:
        """The search form and the saved records that match it (all records when no filter is set)."""
        fields = {name: request.query_params.get(name, "") for name in SEARCH_FIELDS}
        return page(request, "search.html", fields=fields, result=io.search(fields))

    def rules_page(request: Request, values: dict, status_code: int = 200, **context) -> HTMLResponse:
        return page(request, "rules.html", status_code, fields=RULE_FIELDS, values=values, **context)

    @app.get("/rules", response_class=HTMLResponse)
    def rules(request: Request) -> HTMLResponse:
        """The rule thresholds the next assessment will use."""
        values = logic.config.to_dict() if logic is not None else {}
        return rules_page(request, values)

    @app.post("/rules", response_class=HTMLResponse)
    async def save_rules(request: Request) -> HTMLResponse:
        """Apply the typed thresholds, or show why they were refused and keep what was typed."""
        if logic is None:
            return rules_page(request, {}, 503, error=NO_LOGIC)
        form = await request.form()
        typed = {key: str(form.get(key, "")) for key in RULE_FIELDS}
        if form.get("reset"):
            typed = {}
        try:
            config = logic.configure(typed)
        except ValueError as error:
            return rules_page(request, typed, 422, error=str(error))
        return rules_page(request, config.to_dict(), info="Rule settings saved. They apply to the next assessment.")

    return app
