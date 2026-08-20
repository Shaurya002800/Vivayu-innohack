"""Run Vivayu's local browser dashboard for research-mode sensor monitoring."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from vivayu_runtime import ReadingValidationError, RollingPredictor


PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vivayu Research Monitor</title>
  <style>
    :root { --ink:#172033; --muted:#64748b; --line:#d8e0ea; --good:#15803d; --warm:#c2410c; --soft:#f5f7fa; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:#fff; font:15px Arial,sans-serif; }
    header { border-bottom:1px solid var(--line); padding:18px 28px; display:flex; justify-content:space-between; align-items:center; }
    h1 { margin:0; font-size:24px; font-weight:700; letter-spacing:0; }
    .badge { color:#9a3412; background:#fff7ed; border:1px solid #fed7aa; padding:5px 8px; font-size:12px; }
    main { max-width:1160px; margin:0 auto; padding:24px 28px 40px; }
    .notice { border-left:4px solid var(--warm); background:#fff7ed; padding:12px 14px; color:#7c2d12; margin-bottom:20px; line-height:1.45; }
    .grid { display:grid; grid-template-columns:1.05fr .95fr; gap:18px; }
    section { border:1px solid var(--line); padding:18px; min-width:0; }
    h2 { font-size:17px; margin:0 0 12px; }
    p { color:var(--muted); line-height:1.45; }
    textarea { width:100%; min-height:92px; resize:vertical; border:1px solid #94a3b8; border-radius:4px; padding:10px; font:13px ui-monospace,monospace; color:var(--ink); }
    .actions { display:flex; gap:8px; margin-top:10px; }
    button { border:1px solid #0f766e; background:#0f766e; color:#fff; border-radius:4px; padding:9px 12px; cursor:pointer; font-weight:700; }
    button.secondary { background:#fff; color:#0f766e; }
    button:hover { filter:brightness(.96); }
    .stat-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); border-top:1px solid var(--line); border-left:1px solid var(--line); }
    .stat { padding:13px; border-right:1px solid var(--line); border-bottom:1px solid var(--line); }
    .stat strong { display:block; font-size:20px; margin-top:4px; }
    .label { color:var(--muted); font-size:12px; }
    .result { background:var(--soft); border-left:4px solid #64748b; padding:14px; margin-top:12px; white-space:pre-wrap; line-height:1.5; }
    .result.high,.result.elevated { border-left-color:var(--warm); }
    .result.low { border-left-color:var(--good); }
    table { width:100%; border-collapse:collapse; margin-top:12px; font-size:13px; }
    th,td { text-align:left; padding:8px; border-bottom:1px solid var(--line); }
    th { color:var(--muted); font-weight:700; }
    .full { margin-top:18px; }
    @media (max-width:760px) { header { padding:16px; } main { padding:18px 16px; } .grid { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <header><h1>Vivayu</h1><span class="badge">RESEARCH MONITOR</span></header>
  <main>
    <div class="grid">
      <section>
        <h2>Add sensor reading</h2>
        <p>Paste one ESP32 payload. The dashboard predicts after five valid readings.</p>
        <textarea id="payload" spellcheck="false" placeholder="timestamp_ms,temperature_c,humidity_pct,pressure_pa,gas_resistance_ohm,sraw"></textarea>
        <div class="actions"><button id="add">Add reading</button><button id="reset" class="secondary">Reset window</button></div>
        <div id="message" class="result">Awaiting the first reading.</div>
      </section>
      <section>
        <h2>Current research result</h2>
        <div class="stat-grid">
          <div class="stat"><span class="label">Window</span><strong id="window">0 / 5</strong></div>
          <div class="stat"><span class="label">Pattern</span><strong id="pattern">Awaiting</strong></div>
          <div class="stat"><span class="label">Risk level</span><strong id="risk">-</strong></div>
          <div class="stat"><span class="label">Decision confidence</span><strong id="confidence">-</strong></div>
        </div>
        <p id="model">Model: loading...</p>
      </section>
    </div>
    <section class="full">
      <h2>Buffered readings</h2>
      <table><thead><tr><th>#</th><th>Temperature</th><th>Humidity</th><th>Gas resistance</th><th>sraw</th></tr></thead><tbody id="rows"><tr><td colspan="5">No readings yet.</td></tr></tbody></table>
    </section>
  </main>
  <script>
    const payload = document.getElementById('payload');
    const message = document.getElementById('message');
    const body = document.getElementById('rows');
    function show(data) {
      if (data.error) { message.className='result elevated'; message.textContent=data.error; return; }
      message.className='result ' + (data.risk_level || '');
      if (data.status === 'collecting_readings') {
        document.getElementById('window').textContent = data.readings_received + ' / 5';
        message.textContent = 'Reading accepted. Need ' + data.readings_needed + ' more reading(s).';
      } else if (data.status === 'ready') {
        document.getElementById('window').textContent = (data.readings || []).length + ' / 5';
        document.getElementById('model').textContent = 'Model: ' + data.model_name + ' (research candidate)';
        message.textContent = 'Dashboard ready. Paste the first sensor payload.';
      } else if (data.status === 'research_monitoring_only') {
        document.getElementById('window').textContent = '5 / 5';
        document.getElementById('pattern').textContent = data.pattern;
        document.getElementById('risk').textContent = data.risk_level;
        document.getElementById('confidence').textContent = data.confidence_pct + '%';
        document.getElementById('model').textContent = 'Model: ' + data.model_name + ' (research candidate)';
        message.textContent = 'Five-reading result ready. ' + data.confidence_note;
      } else if (data.status === 'reset') {
        document.getElementById('window').textContent = '0 / 5'; document.getElementById('pattern').textContent='Awaiting'; document.getElementById('risk').textContent='-'; document.getElementById('confidence').textContent='-'; message.textContent='Window reset.';
      }
      if (data.readings) {
        body.innerHTML = data.readings.map((r,i) => '<tr><td>'+(i+1)+'</td><td>'+r.temperature_c.toFixed(2)+' C</td><td>'+r.humidity_pct.toFixed(2)+' %</td><td>'+r.gas_resistance_ohm.toFixed(0)+' ohm</td><td>'+r.sraw+'</td></tr>').join('');
      }
    }
    async function send(path, data) {
      const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data || {})});
      const result = await response.json(); show(result); return result;
    }
    document.getElementById('add').onclick = async () => { if (!payload.value.trim()) { show({error:'Paste a sensor payload first.'}); return; } const result=await send('/api/reading',{payload:payload.value}); if (!result.error) payload.value=''; };
    document.getElementById('reset').onclick = () => send('/api/reset');
    fetch('/api/health').then(r=>r.json()).then(show);
  </script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    predictor: RollingPredictor

    def send_json(self, status: HTTPStatus, payload: dict) -> None:
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/health":
            self.send_json(
                HTTPStatus.OK,
                {
                    "status": "ready",
                    "model_name": self.predictor.model_name,
                    "window_size": self.predictor.window_size,
                    "readings": list(self.predictor.readings),
                },
            )
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length) or b"{}")
            if self.path == "/api/reading":
                result = self.predictor.add_reading(payload.get("payload", payload))
                result["readings"] = list(self.predictor.readings)
                self.send_json(HTTPStatus.OK, result)
                return
            if self.path == "/api/reset":
                self.predictor.reset()
                self.send_json(HTTPStatus.OK, {"status": "reset", "readings": []})
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        except (json.JSONDecodeError, ReadingValidationError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def log_message(self, _format: str, *_args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--model",
        default=Path("models/vivayu_research_candidate.joblib"),
        type=Path,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    DashboardHandler.predictor = RollingPredictor(args.model)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Vivayu dashboard: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
