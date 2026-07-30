"""
Observability sloj - pravi OpenTelemetry SDK, ne rucno pisano logiranje.

Zasto OpenTelemetry a ne Langfuse: OTel radi potpuno lokalno (nema
accounta, nema self-hosted servera), a i dalje je jedan od dva imenovana
alata u zadatku. Langfuse bi bio prirodniji izbor u produkciji bas zbog
LLM-specificnih uvida (cost/prompt tracing) - vidi README.

Dvije stvari izlaze iz svakog spana:
  1. Pravi OTel span (console exporter - vidis ga uzivo u terminalu, i
     nas vlastiti JSONLFileSpanExporter - isti span zavrsi kao red u
     logs/trace.jsonl, ali kroz OTel-ov export pipeline, ne rucnim pisanjem).
  2. TraceEvent (models.py) koji se sprema izravno na RequestRecord.trace_events
     - tako "zasto je sustav ovo odlucio" mozes odgovoriti citajuci jedan
     perzistirani zapis zahtjeva, bez trazenja po OTel backendu.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Status, StatusCode

from models import TraceEvent

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
_TRACE_FILE = LOG_DIR / "trace.jsonl"

logger = logging.getLogger("ht_multiagent")
logger.setLevel(logging.INFO)


class JSONLFileSpanExporter(SpanExporter):
    """Vlastiti OTel exporter - jedini 'custom' dio, ostalo je SDK.

    OTel ne dolazi s ugradenim exporterom koji pise JSON Lines u file (samo
    Console, OTLP-za-collector, itd), pa napravimo najmanji moguci: primi gotove
    spanove i za svaki upise jedan JSON red na disk.
    """

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with _TRACE_FILE.open("a", encoding="utf-8") as f:
            for span in spans:
                ctx = span.get_span_context()
                line = {
                    "trace_id": format(ctx.trace_id, "032x"),
                    "span_id": format(ctx.span_id, "016x"),
                    "agent": span.name,
                    "status": span.status.status_code.name,
                    "attributes": dict(span.attributes or {}),
                    "events": [
                        {"name": e.name, "attributes": dict(e.attributes or {})}
                        for e in span.events
                    ],
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                }
                f.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


_provider = TracerProvider(resource=Resource.create({"service.name": "ht-multiagent-zadatak"}))
_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
_provider.add_span_processor(SimpleSpanProcessor(JSONLFileSpanExporter()))
trace.set_tracer_provider(_provider)

_otel_tracer = trace.get_tracer("ht_multiagent")


def new_id(prefix: str) -> str:
    """npr. new_id('trace') -> 'trace_a1b2c3d4e5f6' - nas business ID
    (koristi se za request_id/trace_id na RequestRecord), odvojen od
    OTel-ovog vlastitog trace_id/span_id koji su 128-bitni/64-bitni brojevi."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Tracer:
    """Prikuplja TraceEvent-e za jedan zahtjev, uz OTel span po koraku agenta."""

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.events: list[TraceEvent] = []

    @contextmanager
    def span(self, agent: str) -> Iterator["_Span"]:
        # record_exception/set_status_on_exception iskljuceni jer to radimo
        # rucno u except grani ispod - inace OTel sam upise "exception" event
        # PA i mi, dupli zapis za istu gresku.
        with _otel_tracer.start_as_current_span(
            agent, record_exception=False, set_status_on_exception=False
        ) as otel_span:
            otel_span.set_attribute("business.trace_id", self.trace_id)
            span_id = format(otel_span.get_span_context().span_id, "016x")
            self._record(agent, span_id, "span_start", {})
            try:
                yield _Span(self, agent, span_id, otel_span)
            except Exception as exc:
                otel_span.record_exception(exc)
                otel_span.set_status(Status(StatusCode.ERROR, str(exc)))
                self._record(agent, span_id, "span_error", {"error": str(exc), "type": type(exc).__name__})
                raise
            else:
                otel_span.set_status(Status(StatusCode.OK))
                self._record(agent, span_id, "span_end", {})

    def _record(self, agent: str, span_id: str, event: str, data: dict[str, Any]) -> None:
        te = TraceEvent(span_id=span_id, agent=agent, event=event, data=data)
        self.events.append(te)
        logger.info("[%s] %s/%s :: %s %s", self.trace_id, agent, event, span_id, data)


class _Span:
    """Rucka koju agent dobije unutar 'with tracer.span(...) as span:' bloka."""

    def __init__(self, tracer: Tracer, agent: str, span_id: str, otel_span):
        self._tracer = tracer
        self._agent = agent
        self._span_id = span_id
        self._otel_span = otel_span

    def log(self, event: str, **data: Any) -> None:
        self._otel_span.add_event(event, attributes={k: str(v) for k, v in data.items()})
        self._tracer._record(self._agent, self._span_id, event, data)
