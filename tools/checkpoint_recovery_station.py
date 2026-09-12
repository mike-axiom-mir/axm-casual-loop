#!/usr/bin/env python3
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from causal_loop.checkpoint_inventory import inspect_checkpoint_store
from causal_loop.checkpoint_selection import (
    CHECKPOINT_SELECTION_SCHEMA,
    prepare_checkpoint_resume,
)
from causal_loop.checkpoint_store import LocalCheckpointStore

MAX_REQUEST_BYTES = 8192

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>AXM Causal Loop · Checkpoint Recovery Station</title>
<style>
:root{
  color-scheme:dark;--ink:#eaf5ff;--muted:#8faabd;--panel:#0a1420;--panel2:#0d1b29;
  --line:#2e5368;--cyan:#58e4ff;--gold:#ffd36a;--hold:#ff8e76;--ok:#85f0be;
  --shadow:0 18px 60px rgba(0,0,0,.38)
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:#040a10;color:var(--ink);font:15px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background:
 radial-gradient(circle at 18% 12%,rgba(88,228,255,.09),transparent 31rem),
 linear-gradient(180deg,rgba(255,255,255,.025),transparent 22rem)}
button{font:inherit;color:inherit}
.shell{width:min(1160px,100%);margin:auto;padding:24px}
.mast{display:grid;grid-template-columns:1fr auto;gap:20px;align-items:end;border-bottom:1px solid var(--line);padding-bottom:18px}
.eyebrow{color:var(--cyan);letter-spacing:.18em;font-size:12px;text-transform:uppercase}
h1{font-size:clamp(28px,5vw,54px);line-height:.95;margin:.32rem 0 .7rem;letter-spacing:-.05em}
.lede{max-width:74ch;color:var(--muted);margin:0}
.truth{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.pill{border:1px solid var(--line);padding:7px 9px;border-radius:999px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;background:#07111a}
.pill.ok{color:var(--ok);border-color:#2a6c58}.pill.gold{color:var(--gold);border-color:#725f2a}
.grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,.8fr);gap:16px;margin-top:18px}
.panel{min-width:0;background:linear-gradient(180deg,rgba(15,31,46,.95),rgba(7,16,24,.96));border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);overflow:hidden}
.panel-head{display:flex;min-width:0;justify-content:space-between;gap:14px;align-items:center;padding:15px 16px;border-bottom:1px solid rgba(46,83,104,.7)}
.panel-head>*{min-width:0}
.panel-head h2{margin:0;font-size:14px;letter-spacing:.13em;text-transform:uppercase}
.meta{color:var(--muted);font-size:12px;max-width:100%;white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.controls{display:flex;gap:8px;flex-wrap:wrap}
.btn{min-height:44px;border:1px solid var(--line);background:#0a1a27;border-radius:9px;padding:10px 13px;cursor:pointer}
.btn:hover{border-color:var(--cyan)}.btn:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
.btn.primary{border-color:#2b8294;background:#0d2b35}.btn.copy{border-color:#5d532a}
.btn[disabled]{opacity:.46;cursor:not-allowed}
.station{padding:16px}
.overview{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}
.metric{padding:11px;border:1px solid rgba(46,83,104,.75);border-radius:10px;background:#07121b}
.metric b{display:block;font-size:22px}.metric span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.hash{max-width:100%;white-space:normal;overflow-wrap:anywhere;word-break:break-all;color:#b9d4e2;font-size:12px}
.track{position:relative;display:grid;gap:10px;padding-left:22px}
.track:before{content:"";position:absolute;left:7px;top:8px;bottom:8px;width:2px;background:linear-gradient(var(--cyan),rgba(88,228,255,.12))}
.candidate{position:relative;min-width:0;border:1px solid rgba(46,83,104,.8);border-radius:12px;padding:13px;background:#081721}
.candidate:before{content:"";position:absolute;left:-21px;top:20px;width:12px;height:12px;border:2px solid var(--cyan);border-radius:50%;background:#06101a}
.candidate[data-selected="true"]{border-color:var(--gold);box-shadow:0 0 0 1px rgba(255,211,106,.22) inset}
.row{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.row>*{min-width:0}
.kicker{color:var(--gold);font-size:11px;letter-spacing:.12em;text-transform:uppercase}
.progress{height:5px;background:#061019;border-radius:999px;overflow:hidden;margin:10px 0}
.progress span{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--gold));transform-origin:left}
.small{color:var(--muted);font-size:12px;max-width:100%;white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.plan{padding:16px;min-height:240px;min-width:0}
.state-banner{border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:13px}
.state-banner strong{display:block;letter-spacing:.12em;text-transform:uppercase;font-size:12px}
.state-banner span{overflow-wrap:anywhere;word-break:break-word}
.state-banner.ready{border-color:#2a6c58;background:rgba(42,108,88,.12)}
.state-banner.hold{border-color:#834a3d;background:rgba(131,74,61,.13)}
.state-banner.idle{border-color:#4a6576}
.plan-grid{display:grid;gap:10px;min-width:0}
.fact{border-left:2px solid var(--line);padding-left:10px;min-width:0}
.fact label{display:block;color:var(--muted);font-size:10px;letter-spacing:.1em;text-transform:uppercase}
.fact>div{max-width:100%;white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.next{margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}
.held{margin-top:16px;border-top:1px solid var(--line);padding-top:14px}
.held details{background:#100e10;border:1px solid #533b3b;border-radius:10px;padding:10px}
.empty{padding:26px;color:var(--muted);text-align:center;border:1px dashed var(--line);border-radius:10px}
footer{color:var(--muted);font-size:11px;padding:18px 2px;text-align:center}
.sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:780px){
 .shell{padding:12px}.mast{grid-template-columns:1fr}.truth{justify-content:flex-start}
 .grid{grid-template-columns:1fr}.panel{border-radius:13px}.overview{grid-template-columns:repeat(3,1fr)}
 .panel-head{align-items:flex-start;flex-direction:column}.controls{width:100%}.controls .btn{flex:1}
 .row{flex-direction:column}.candidate .btn{width:100%}.plan{min-height:0}
}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
@media(prefers-contrast:more){:root{--line:#79a5bc}.panel,.candidate,.metric{border-width:2px}}
</style>
</head>
<body>
<main class="shell">
  <header class="mast">
    <div>
      <div class="eyebrow">AXM Causal Loop Fabric · local recovery surface</div>
      <h1>Checkpoint<br>Recovery Station</h1>
      <p class="lede">Inspect verified persisted causal checkpoints, make one explicit choice, and prepare the existing deterministic resume plan. This station never chooses “latest” and never resumes the engine.</p>
    </div>
    <div class="truth" aria-label="Authority boundaries">
      <span class="pill ok">Local / offline</span>
      <span class="pill gold">Explicit selection only</span>
      <span class="pill">Display ≠ resume authority</span>
    </div>
  </header>

  <section class="grid">
    <div class="panel">
      <div class="panel-head">
        <div><h2>Persisted checkpoint line</h2><div class="meta" id="setMeta">Scanning exact local store…</div></div>
        <div class="controls"><button class="btn" id="refresh">Refresh evidence</button></div>
      </div>
      <div class="station">
        <div class="overview">
          <div class="metric"><b id="candidateCount">—</b><span>Verified</span></div>
          <div class="metric"><b id="heldCount">—</b><span>Held</span></div>
          <div class="metric"><b id="tempCount">—</b><span>Temp traces</span></div>
        </div>
        <div id="candidateTrack" class="track" aria-label="Verified checkpoint candidates"></div>
        <div id="heldArea" class="held"></div>
      </div>
    </div>

    <aside class="panel">
      <div class="panel-head"><div><h2>Exact handoff</h2><div class="meta">No automatic selection · no resume</div></div></div>
      <div class="plan" id="planPanel">
        <div class="state-banner idle" id="planBanner"><strong>No checkpoint selected</strong><span>Choose one verified candidate to prepare a caller-pinned handoff.</span></div>
        <div class="plan-grid" id="planFacts"></div>
        <div class="next">
          <button class="btn copy" id="copyPlan" disabled>Copy exact plan JSON</button>
          <p class="small" id="nextAction">The engine’s existing resume admission remains the next authority after this station.</p>
        </div>
      </div>
    </aside>
  </section>
  <footer>Inventory order is content-hash order, not preference, freshness, or quality. SHA-256 is identity evidence, not authorship.</footer>
  <div class="sr" id="announce" aria-live="polite"></div>
</main>
<script>
(() => {
  const $ = (id) => document.getElementById(id);
  let inventory = null;
  let preparedPlan = null;
  let selectedHash = null;

  const short = (value) => typeof value === 'string' ? `${value.slice(0,8)}…${value.slice(-8)}` : '—';
  const text = (el, value) => { el.textContent = value; };
  const fact = (label, value, exact=false) => {
    const node = document.createElement('div'); node.className='fact';
    const l=document.createElement('label'); l.textContent=label;
    const v=document.createElement('div'); v.className=exact?'hash':''; v.textContent=value ?? '—';
    node.append(l,v); return node;
  };
  const announce = (message) => text($('announce'), message);

  function clearPlan(message='Choose one verified candidate to prepare a caller-pinned handoff.') {
    preparedPlan=null; selectedHash=null; $('copyPlan').disabled=true;
    $('planBanner').className='state-banner idle';
    $('planBanner').innerHTML='<strong>No checkpoint selected</strong><span></span>';
    $('planBanner').querySelector('span').textContent=message;
    $('planFacts').replaceChildren();
    document.querySelectorAll('.candidate').forEach(n=>n.dataset.selected='false');
  }

  function holdPlan(message) {
    preparedPlan=null; $('copyPlan').disabled=true;
    $('planBanner').className='state-banner hold';
    $('planBanner').innerHTML='<strong>Selection held</strong><span></span>';
    $('planBanner').querySelector('span').textContent=message;
    $('planFacts').replaceChildren();
    $('planFacts').append(fact('Next honest action','Refresh evidence, review the changed candidate set, then choose explicitly again.'));
    announce(`Selection held. ${message}`);
  }

  function renderInventory(data) {
    inventory=data;
    text($('candidateCount'), data.candidateCount);
    text($('heldCount'), data.heldCount);
    text($('tempCount'), data.diagnostics.abandonedTempCount);
    text($('setMeta'), `Candidate set ${short(data.candidateSetHash)} · ${data.authority}`);
    const track=$('candidateTrack'); track.replaceChildren();
    if (!data.candidates.length) {
      const empty=document.createElement('div'); empty.className='empty';
      empty.textContent='No verified persisted checkpoints are currently selectable.';
      track.append(empty);
    } else {
      data.candidates.forEach((c, index) => {
        const card=document.createElement('article'); card.className='candidate'; card.dataset.selected='false';
        const row=document.createElement('div'); row.className='row';
        const info=document.createElement('div');
        const k=document.createElement('div'); k.className='kicker'; k.textContent=`Checkpoint ${index+1} · ${c.wavesExecuted ?? '—'} / ${c.maxWaves ?? '—'} waves`;
        const h=document.createElement('div'); h.className='hash'; h.textContent=c.checkpointHash;
        const s=document.createElement('div'); s.className='small'; s.textContent=`Run ${short(c.runId)} · state ${short(c.stateHash)} · loop ${c.loopId ?? '—'} ${c.loopVersion ?? ''}`;
        info.append(k,h,s);
        const b=document.createElement('button'); b.className='btn primary'; b.type='button'; b.textContent='Prepare exact plan';
        b.dataset.checkpoint=c.checkpointHash; b.setAttribute('aria-label',`Prepare exact plan for checkpoint ${c.checkpointHash}`);
        b.addEventListener('click',()=>prepare(c.checkpointHash, card));
        row.append(info,b); card.append(row);
        const p=document.createElement('div'); p.className='progress'; p.setAttribute('aria-hidden','true');
        const fill=document.createElement('span');
        const denom=Number(c.maxWaves)||0, numer=Number(c.wavesExecuted)||0;
        fill.style.width=denom>0?`${Math.max(0,Math.min(100,(numer/denom)*100))}%`:'0%';
        p.append(fill); card.append(p);
        const cap=document.createElement('div'); cap.className='small'; cap.textContent='Recorded causal depth only · not a recommendation';
        card.append(cap); track.append(card);
      });
    }
    const held=$('heldArea'); held.replaceChildren();
    if (data.heldCount || data.diagnostics.abandonedTempCount || data.diagnostics.ignoredEntryCount) {
      const d=document.createElement('details'); const s=document.createElement('summary');
      s.textContent=`Non-candidates · ${data.heldCount} held · ${data.diagnostics.abandonedTempCount} temp · ${data.diagnostics.ignoredEntryCount} ignored`;
      d.append(s);
      data.held.forEach(item=>{const p=document.createElement('p');p.className='hash';p.textContent=`${item.checkpointHash} · ${item.reason}`;d.append(p)});
      held.append(d);
    }
  }

  async function loadInventory() {
    $('refresh').disabled=true;
    try {
      const response=await fetch('/api/inventory',{cache:'no-store'});
      const data=await response.json();
      if(!response.ok) throw new Error(data.error||`HTTP ${response.status}`);
      renderInventory(data); clearPlan('Evidence refreshed. Choose one verified candidate explicitly.');
      announce(`Evidence refreshed. ${data.candidateCount} verified checkpoints, ${data.heldCount} held.`);
    } catch (error) {
      holdPlan(`Inventory unavailable: ${error.message}`);
      text($('setMeta'),'Inventory unavailable · no selection authority');
    } finally {$('refresh').disabled=false}
  }

  async function prepare(checkpointHash, card) {
    if(!inventory) return;
    selectedHash=checkpointHash;
    document.querySelectorAll('.candidate').forEach(n=>n.dataset.selected='false'); card.dataset.selected='true';
    $('copyPlan').disabled=true;
    $('planBanner').className='state-banner idle';
    $('planBanner').innerHTML='<strong>Revalidating exact choice</strong><span>Re-scanning the store before a plan can exist…</span>';
    try {
      const response=await fetch('/api/prepare',{
        method:'POST',headers:{'content-type':'application/json'},
        body:JSON.stringify({schema:'axm.causal-loop.checkpoint-selection/v0.01',candidateSetHash:inventory.candidateSetHash,checkpointHash})
      });
      const data=await response.json();
      if(!response.ok){ if(data.inventory) renderInventory(data.inventory); throw new Error(data.error||`HTTP ${response.status}`) }
      preparedPlan=data.plan;
      const r=data.plan.receipt;
      $('planBanner').className='state-banner ready';
      $('planBanner').innerHTML='<strong>Plan ready · not resumed</strong><span>Exact store evidence still matched your explicit choice.</span>';
      $('planFacts').replaceChildren(
        fact('Checkpoint',r.selection.checkpointHash,true),
        fact('Candidate set',r.selection.candidateSetHash,true),
        fact('Plan identity',r.planHash,true),
        fact('Recorded causal depth',`${r.candidate.wavesExecuted} / ${r.candidate.maxWaves} waves`),
        fact('Authority',r.authority)
      );
      $('copyPlan').disabled=false;
      announce('Exact resume plan prepared. The engine has not resumed.');
    } catch (error) {
      holdPlan(error.message);
    }
  }

  $('refresh').addEventListener('click',loadInventory);
  $('copyPlan').addEventListener('click',async()=>{
    if(!preparedPlan)return;
    try{
      await navigator.clipboard.writeText(JSON.stringify(preparedPlan));
      text($('nextAction'),'Exact plan JSON copied. A caller may now hand it to the existing engine resume path, which will revalidate the checkpoint prefix.');
      announce('Exact plan JSON copied. No resume was executed.');
    }catch{
      text($('nextAction'),'Clipboard unavailable. The plan remains prepared in this tab; no fallback download or hidden write occurred.');
      announce('Clipboard unavailable. No hidden write occurred.');
    }
  });
  loadInventory();
})();
</script>
</body>
</html>"""


class RecoveryStation:
    def __init__(self, store: LocalCheckpointStore):
        self.store = store

    def inventory(self) -> dict[str, Any]:
        return inspect_checkpoint_store(self.store)

    def prepare(self, payload: dict[str, Any]) -> dict[str, Any]:
        return prepare_checkpoint_resume(self.store, payload)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def make_handler(station: RecoveryStation):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AXMCheckpointRecovery/0.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            route = urlparse(self.path).path
            if route == "/":
                self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if route == "/api/inventory":
                try:
                    body = _json_bytes(station.inventory())
                except (OSError, ValueError) as exc:
                    self._send(409, _json_bytes({"error": str(exc)}), "application/json")
                else:
                    self._send(200, body, "application/json")
                return
            self._send(404, b'{"error":"not found"}', "application/json")

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/prepare":
                self._send(404, b'{"error":"not found"}', "application/json")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._send(413, b'{"error":"request body outside bounded size"}', "application/json")
                return
            if self.headers.get_content_type() != "application/json":
                self._send(415, b'{"error":"application/json required"}', "application/json")
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("selection must be one JSON object")
                plan = station.prepare(payload)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OSError) as exc:
                response = {"error": str(exc)}
                try:
                    response["inventory"] = station.inventory()
                except (OSError, ValueError):
                    pass
                self._send(409, _json_bytes(response), "application/json")
                return
            self._send(200, _json_bytes({"plan": plan}), "application/json")

    return Handler


def build_server(store_path: str | Path, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("recovery station must remain loopback-only")
    store = LocalCheckpointStore(store_path)
    return ThreadingHTTPServer((host, port), make_handler(RecoveryStation(store)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the local AXM Causal Loop checkpoint recovery station.")
    parser.add_argument("--store", required=True, help="LocalCheckpointStore directory")
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1"], help="Loopback only")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = build_server(args.store, args.host, args.port)
    host, port = server.server_address[:2]
    print(f"AXM checkpoint recovery station: http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
