from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causal_loop.atlas_verifier import verify_atlas
from causal_loop.train_platform import build_engine


def _strict_load_json(path: Path) -> Mapping[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON value: {value}")
        ),
    )
    if not isinstance(value, Mapping):
        raise ValueError("atlas root must be an object")
    return value


def _safe_json_for_html(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _projection(atlas: Mapping[str, Any], verification: Mapping[str, Any]) -> dict[str, Any]:
    path_sizes = {key: len(value) for key, value in atlas["pathGroups"].items()}
    endpoint_sizes = {key: len(value) for key, value in atlas["endStateGroups"].items()}
    cases = []
    for case in atlas["cases"]:
        cases.append(
            {
                "caseId": case["caseId"],
                "status": case["status"],
                "failureReason": case["failureReason"],
                "deterministicRepeat": case["deterministicRepeat"],
                "timedExternalInfluences": case["timedExternalInfluences"],
                "appliedTimedInfluences": case["appliedTimedInfluences"],
                "unappliedTimedInfluences": case["unappliedTimedInfluences"],
                "receiptHash": case["receiptHash"],
                "realizedPathHash": case["realizedPathHash"],
                "endStateHash": case["endStateHash"],
                "causalDepth": case["causalDepth"],
                "transitionCount": case["transitionCount"],
                "moduleActivationCount": case["moduleActivationCount"],
                "contradictionCount": case["contradictionCount"],
                "authorityViolationCount": case["authorityViolationCount"],
                "readViolationCount": case["readViolationCount"],
                "hardInvariantFailures": case["hardInvariantFailures"],
                "orphanExternalWriteKeys": case["orphanExternalWriteKeys"],
                "unresolvedExternalWrites": case["unresolvedExternalWrites"],
                "pathGroupSize": path_sizes[case["realizedPathHash"]],
                "endpointGroupSize": endpoint_sizes[case["endStateHash"]],
            }
        )
    return {
        "schema": "axm.causal-loop.atlas-map-projection/v0.01",
        "authority": "DISPLAY_ONLY_NO_EXECUTION_NO_SELECTION_NO_CANON",
        "atlasHash": atlas["atlasHash"],
        "verificationHash": verification["verificationHash"],
        "loopId": atlas["loopId"],
        "loopVersion": atlas["loopVersion"],
        "engineSignature": atlas["engineSignature"],
        "summary": atlas["summary"],
        "pathGroups": atlas["pathGroups"],
        "endStateGroups": atlas["endStateGroups"],
        "cases": cases,
    }


def render_atlas_map(atlas: Mapping[str, Any]) -> str:
    engine = build_engine()
    verification = verify_atlas(
        atlas,
        expected_engine_signature=engine.engine_signature,
        expected_loop_id=engine.spec.loop_id,
        expected_loop_version=engine.spec.version,
    )
    data = _projection(atlas, verification)
    embedded = _safe_json_for_html(data)
    title_hash = html.escape(atlas["atlasHash"][:12])

    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>AXM Causal Atlas Map · {title_hash}</title>
<style>
:root{{--bg:#070b11;--panel:rgba(18,25,36,.84);--panel2:rgba(9,15,23,.86);--line:rgba(165,199,255,.18);--text:#e8f0ff;--muted:#91a3bf;--glow:#9dd7ff;--gold:#ffd17d;--ok:#9fffbf;--bad:#ff9aa4;--focus:#fff2a8}}
*{{box-sizing:border-box}}
html{{background:var(--bg)}}
body{{margin:0;min-height:100vh;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(circle at 50% -15%,#19334f 0,#0b1420 34%,var(--bg) 72%);color:var(--text)}}
button,input,select{{font:inherit}}
button:focus-visible,input:focus-visible,select:focus-visible{{outline:3px solid var(--focus);outline-offset:3px}}
.shell{{max-width:1240px;margin:auto;padding:22px}}
.top{{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap;margin-bottom:18px}}
.brand{{display:flex;gap:12px;align-items:center}}.mark{{width:44px;height:44px;border:1px solid rgba(157,215,255,.45);border-radius:14px;background:linear-gradient(145deg,rgba(157,215,255,.18),rgba(157,215,255,.03));display:grid;place-items:center;font-weight:850;box-shadow:0 0 28px rgba(104,185,255,.16)}}h1{{font-size:20px;margin:0}}.sub{{font-size:12px;color:var(--muted);margin-top:5px;line-height:1.5}}.badge{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:9px 12px;border:1px solid rgba(159,255,191,.34);border-radius:999px;color:var(--ok);background:rgba(57,120,78,.12)}}
.summary{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:14px}}.metric{{border:1px solid var(--line);border-radius:14px;background:linear-gradient(160deg,rgba(27,39,55,.8),rgba(10,15,23,.9));padding:13px;min-width:0}}.label{{font-size:10px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted)}}.big{{font-size:24px;font-weight:790;margin-top:5px;font-variant-numeric:tabular-nums}}.small{{font-size:11px;color:var(--muted);line-height:1.55}}
.grid{{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(330px,.65fr);gap:14px}}.card{{border:1px solid var(--line);border-radius:18px;background:linear-gradient(160deg,rgba(27,39,55,.82),rgba(10,15,23,.9));box-shadow:0 18px 60px rgba(0,0,0,.24);overflow:hidden}}.pad{{padding:16px}}
.toolbar{{display:grid;grid-template-columns:1.3fr .8fr .8fr;gap:10px;margin-bottom:13px}}.control{{display:grid;gap:6px}}input,select{{width:100%;min-height:44px;border:1px solid rgba(181,213,255,.22);border-radius:10px;background:#0d1824;color:var(--text);padding:9px 11px}}
.endpointRail{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-bottom:13px}}.endpoint{{min-height:58px;text-align:left;border:1px solid rgba(181,213,255,.17);border-radius:12px;background:rgba(10,18,27,.72);color:var(--text);padding:10px;cursor:pointer}}.endpoint[aria-pressed="true"]{{border-color:rgba(157,215,255,.72);box-shadow:inset 0 0 0 1px rgba(157,215,255,.24),0 0 22px rgba(104,185,255,.12)}}.endpoint .count{{display:block;font-size:17px;font-weight:760;margin-top:3px}}.endpoint .hash{{display:block;font:9px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);overflow:hidden;text-overflow:ellipsis}}
.caseList{{display:grid;gap:8px;max-height:520px;overflow:auto;padding-right:3px}}.case{{width:100%;min-height:54px;text-align:left;border:1px solid rgba(181,213,255,.14);border-radius:12px;background:rgba(8,15,23,.62);color:var(--text);padding:10px 12px;cursor:pointer;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:center}}.case[aria-current="true"]{{border-color:rgba(255,209,125,.72);box-shadow:inset 3px 0 var(--gold)}}.caseName{{font-size:12px;font-weight:690;overflow-wrap:anywhere}}.caseMeta{{font-size:10px;color:var(--muted);margin-top:4px}}.pill{{font-size:9px;text-transform:uppercase;letter-spacing:.08em;border:1px solid rgba(159,255,191,.25);color:var(--ok);border-radius:999px;padding:5px 7px;white-space:nowrap}}
.receiptTitle{{font-size:15px;font-weight:760;margin-top:5px;overflow-wrap:anywhere}}.direction{{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}}.directionChip{{border:1px solid rgba(255,209,125,.28);background:rgba(255,209,125,.06);color:#ffe2a8;border-radius:999px;padding:7px 9px;font-size:11px}}.emptyDirection{{color:var(--muted);font-size:11px;margin-top:12px}}
.factGrid{{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}}.fact{{border:1px solid rgba(181,213,255,.12);border-radius:12px;background:rgba(5,10,16,.38);padding:11px}}.value{{font-size:15px;font-weight:720;margin-top:4px;overflow-wrap:anywhere}}.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;word-break:break-all}}
.compare{{margin-top:13px;padding-top:13px;border-top:1px solid var(--line)}}.compare button{{min-height:44px;width:100%;border:1px solid rgba(157,215,255,.28);border-radius:10px;background:rgba(18,32,47,.8);color:var(--text);padding:9px 11px;cursor:pointer}}.compareBox{{margin-top:9px;border:1px solid rgba(157,215,255,.15);border-radius:12px;padding:11px;background:rgba(6,12,19,.5)}}.same{{color:var(--ok)}}.different{{color:var(--gold)}}.held{{color:var(--bad)}}
.boundary{{margin-top:13px;padding:12px;border-left:2px solid rgba(255,209,125,.48);background:rgba(255,209,125,.04);font-size:11px;line-height:1.55;color:var(--muted)}}.identity{{margin-top:13px;padding-top:12px;border-top:1px solid var(--line)}}.identityRow{{display:grid;grid-template-columns:86px minmax(0,1fr);gap:8px;margin-top:7px;align-items:start}}
.statusline{{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:9px}}#visibleCount{{font-size:11px;color:var(--muted)}}
@media(max-width:900px){{.summary{{grid-template-columns:repeat(2,1fr)}}.summary .metric:last-child{{grid-column:1/-1}}.grid{{grid-template-columns:1fr}}}}
@media(max-width:620px){{.shell{{padding:13px}}.toolbar{{grid-template-columns:1fr}}.endpointRail{{grid-template-columns:1fr 1fr}}.summary{{gap:8px}}.big{{font-size:21px}}.caseList{{max-height:420px}}.factGrid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:380px){{.factGrid{{grid-template-columns:1fr}}}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}}}
@media(prefers-contrast:more){{:root{{--line:rgba(220,235,255,.44);--muted:#b9c7dc}}}}
</style>
</head>
<body>
<main class="shell">
  <header class="top">
    <div class="brand"><div class="mark">AX</div><div><h1>Causal Atlas Map</h1><div class="sub">Explore bounded directions → realized path identity → endpoint identity without granting the display causal authority.</div></div></div>
    <div class="badge">Verified structure · display only</div>
  </header>

  <section class="summary" aria-label="Atlas summary">
    <div class="metric"><div class="label">Cases</div><div class="big" id="caseCount">—</div><div class="small">bounded schedules exercised</div></div>
    <div class="metric"><div class="label">Realized paths</div><div class="big" id="pathCount">—</div><div class="small">distinct path hashes</div></div>
    <div class="metric"><div class="label">Endpoints</div><div class="big" id="endpointCount">—</div><div class="small">distinct end-state hashes</div></div>
    <div class="metric"><div class="label">Failures</div><div class="big" id="failureCount">—</div><div class="small">explicit failed cases</div></div>
    <div class="metric"><div class="label">Determinism</div><div class="big" id="repeatState">—</div><div class="small">repeat mismatches</div></div>
  </section>

  <div class="grid">
    <section class="card pad">
      <div class="toolbar">
        <label class="control"><span class="label">Find a schedule</span><input id="search" type="search" placeholder="BLOCK_DOOR, wave 2, pair…" autocomplete="off"></label>
        <label class="control"><span class="label">Shape</span><select id="shape"><option value="all">All shapes</option><option value="empty">Empty</option><option value="single">Single</option><option value="pair">Pair</option><option value="pair-repeat">Repeated action</option><option value="pair-reversed">Reversed same-wave</option></select></label>
        <label class="control"><span class="label">Endpoint</span><select id="endpointFilter"><option value="all">All endpoints</option></select></label>
      </div>
      <div class="label" style="margin-bottom:8px">Endpoint lanes · choose one to narrow</div>
      <div id="endpointRail" class="endpointRail" aria-label="Endpoint groups"></div>
      <div class="statusline"><div class="label">Schedules</div><div id="visibleCount">—</div></div>
      <div id="caseList" class="caseList" role="listbox" aria-label="Bounded schedule cases"></div>
    </section>

    <aside class="card pad" aria-live="polite">
      <div class="label">Selected evidence case</div>
      <div id="selectedTitle" class="receiptTitle">—</div>
      <div id="directions" class="direction"></div>
      <div class="factGrid">
        <div class="fact"><div class="label">Result</div><div id="result" class="value">—</div></div>
        <div class="fact"><div class="label">Applied</div><div id="applied" class="value">—</div></div>
        <div class="fact"><div class="label">Causal depth</div><div id="depth" class="value">—</div></div>
        <div class="fact"><div class="label">Transitions</div><div id="transitions" class="value">—</div></div>
        <div class="fact"><div class="label">Path family</div><div id="pathFamily" class="value">—</div></div>
        <div class="fact"><div class="label">Endpoint family</div><div id="endpointFamily" class="value">—</div></div>
      </div>
      <div class="identity">
        <div class="identityRow"><div class="label">Path</div><div id="pathHash" class="mono">—</div></div>
        <div class="identityRow"><div class="label">Endpoint</div><div id="endHash" class="mono">—</div></div>
        <div class="identityRow"><div class="label">Receipt</div><div id="receiptHash" class="mono">—</div></div>
      </div>
      <div class="compare">
        <button id="compareSibling" type="button">Compare nearest timing sibling</button>
        <div id="compareBox" class="compareBox small">Choose a case to compare its path and endpoint identities with the nearest schedule using the same actions at a nearby wave.</div>
      </div>
      <div class="boundary"><strong>Truth ceiling:</strong> this map is a projection of an Atlas that passed the repository verifier. It does not replay source receipts, select a preferred path, execute actions, commit history, authenticate authorship, merge, or declare CANON. Equal hashes mean equal recorded identities under this Atlas contract; they are not a claim of semantic quality.</div>
    </aside>
  </div>

  <section class="card pad" style="margin-top:14px">
    <div class="label">Evidence identity</div>
    <div class="identityRow"><div class="label">Atlas</div><div id="atlasHash" class="mono">—</div></div>
    <div class="identityRow"><div class="label">Verifier</div><div id="verificationHash" class="mono">—</div></div>
    <div class="identityRow"><div class="label">Engine</div><div id="engineSignature" class="mono">—</div></div>
  </section>
</main>
<script id="atlas-data" type="application/json">{embedded}</script>
<script>
const data=JSON.parse(document.getElementById('atlas-data').textContent);
const $=id=>document.getElementById(id);
let selectedId=data.cases[0]?.caseId||null;
let endpointPressed='all';

function shapeOf(id){{
  if(id==='empty') return 'empty';
  if(id.startsWith('single:')) return 'single';
  if(id.startsWith('pair-repeat:')) return 'pair-repeat';
  if(id.startsWith('pair-reversed:')) return 'pair-reversed';
  return id.startsWith('pair:')?'pair':'other';
}}
function shortHash(value){{return value?value.slice(0,10)+'…':'—'}}
function influenceText(item){{
  const action=item.action||item.source||'direction';
  const wave=item.atWave ?? item.wave ?? '?';
  return `${{action}} @ wave ${{wave}}`;
}}
function caseSearchText(c){{
  return [c.caseId,...c.timedExternalInfluences.map(influenceText),c.status,c.failureReason||''].join(' ').toLowerCase();
}}
function endpointEntries(){{
  return Object.entries(data.endStateGroups).sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]));
}}
function selectedCase(){{return data.cases.find(c=>c.caseId===selectedId)||data.cases[0]}}

function renderSummary(){{
  $('caseCount').textContent=data.summary.caseCount;
  $('pathCount').textContent=data.summary.uniqueRealizedPathCount;
  $('endpointCount').textContent=data.summary.uniqueEndStateCount;
  $('failureCount').textContent=data.summary.failedCount;
  $('repeatState').textContent=data.summary.deterministicMismatchCount===0?'0 drift':`${{data.summary.deterministicMismatchCount}} drift`;
  $('atlasHash').textContent=data.atlasHash;
  $('verificationHash').textContent=data.verificationHash;
  $('engineSignature').textContent=data.engineSignature;
}}

function renderEndpoints(){{
  const entries=endpointEntries();
  $('endpointRail').replaceChildren(...entries.map(([hash,ids],index)=>{{
    const button=document.createElement('button');
    button.type='button';button.className='endpoint';button.dataset.endpoint=hash;
    button.setAttribute('aria-pressed',String(endpointPressed===hash));
    button.setAttribute('aria-label',`Endpoint ${{index+1}}, ${{ids.length}} cases`);
    const count=document.createElement('span');count.className='count';count.textContent=`${{ids.length}} cases`;
    const digest=document.createElement('span');digest.className='hash';digest.textContent=shortHash(hash);
    button.append(document.createTextNode(`Endpoint ${{index+1}}`),count,digest);
    button.onclick=()=>{{
      endpointPressed=endpointPressed===hash?'all':hash;
      $('endpointFilter').value=endpointPressed;
      renderEndpoints();renderCases();
    }};
    return button;
  }}));
  const select=$('endpointFilter');
  if(select.options.length===1){{
    entries.forEach(([hash,ids],index)=>{{
      const option=document.createElement('option');option.value=hash;option.textContent=`Endpoint ${{index+1}} · ${{ids.length}} cases · ${{shortHash(hash)}}`;select.append(option);
    }});
  }}
}}

function filteredCases(){{
  const q=$('search').value.trim().toLowerCase();
  const shape=$('shape').value;
  const endpoint=$('endpointFilter').value;
  return data.cases.filter(c=>(!q||caseSearchText(c).includes(q))&&(shape==='all'||shapeOf(c.caseId)===shape)&&(endpoint==='all'||c.endStateHash===endpoint));
}}

function renderCases(){{
  const visible=filteredCases();
  $('visibleCount').textContent=`${{visible.length}} / ${{data.cases.length}} visible`;
  const list=$('caseList');list.replaceChildren();
  visible.forEach(c=>{{
    const button=document.createElement('button');button.type='button';button.className='case';button.setAttribute('role','option');button.setAttribute('aria-current',String(c.caseId===selectedId));button.setAttribute('aria-selected',String(c.caseId===selectedId));
    const main=document.createElement('div');
    const name=document.createElement('div');name.className='caseName';name.textContent=c.caseId;
    const meta=document.createElement('div');meta.className='caseMeta';meta.textContent=`${{c.timedExternalInfluences.length}} direction${{c.timedExternalInfluences.length===1?'':'s'}} · depth ${{c.causalDepth}} · ${{c.pathGroupSize}} share path`;
    main.append(name,meta);
    const pill=document.createElement('span');pill.className='pill';pill.textContent=c.status;
    button.append(main,pill);
    button.onclick=()=>{{selectedId=c.caseId;renderCases();renderSelected();}};
    button.onkeydown=e=>{{
      if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;
      e.preventDefault();const buttons=[...list.querySelectorAll('.case')];const i=buttons.indexOf(button);let target=i;
      if(e.key==='ArrowDown')target=Math.min(buttons.length-1,i+1);
      if(e.key==='ArrowUp')target=Math.max(0,i-1);
      if(e.key==='Home')target=0;if(e.key==='End')target=buttons.length-1;
      buttons[target]?.focus();
    }};
    list.append(button);
  }});
}}

function renderSelected(){{
  const c=selectedCase();if(!c)return;
  $('selectedTitle').textContent=c.caseId;
  const direction=$('directions');direction.replaceChildren();
  if(!c.timedExternalInfluences.length){{
    const empty=document.createElement('div');empty.className='emptyDirection';empty.textContent='No external direction in this case.';direction.append(empty);
  }}else c.timedExternalInfluences.forEach(item=>{{
    const chip=document.createElement('span');chip.className='directionChip';chip.textContent=influenceText(item);direction.append(chip);
  }});
  $('result').textContent=c.status+(c.failureReason?` · ${{c.failureReason}}`:'');
  $('applied').textContent=`${{c.appliedTimedInfluences.length}} / ${{c.timedExternalInfluences.length}}`;
  $('depth').textContent=c.causalDepth;
  $('transitions').textContent=c.transitionCount;
  $('pathFamily').textContent=`${{c.pathGroupSize}} case${{c.pathGroupSize===1?'':'s'}}`;
  $('endpointFamily').textContent=`${{c.endpointGroupSize}} case${{c.endpointGroupSize===1?'':'s'}}`;
  $('pathHash').textContent=c.realizedPathHash;
  $('endHash').textContent=c.endStateHash;
  $('receiptHash').textContent=c.receiptHash;
  $('compareBox').textContent='Compare this recorded identity with the nearest schedule using the same direction sequence.';
}}

function actionSequence(c){{return c.timedExternalInfluences.map(x=>x.action||x.source||'').join('|')}}
function waveVector(c){{return c.timedExternalInfluences.map(x=>Number(x.atWave??x.wave??0))}}
function nearestSibling(c){{
  const seq=actionSequence(c);const base=waveVector(c);
  let best=null,bestDistance=Infinity;
  for(const other of data.cases){{
    if(other.caseId===c.caseId||actionSequence(other)!==seq||other.timedExternalInfluences.length!==c.timedExternalInfluences.length)continue;
    const waves=waveVector(other);const distance=waves.reduce((sum,w,i)=>sum+Math.abs(w-(base[i]??0)),0);
    if(distance<bestDistance||(distance===bestDistance&&other.caseId<(best?.caseId||'~'))){{best=other;bestDistance=distance;}}
  }}
  return best;
}}
$('compareSibling').onclick=()=>{{
  const c=selectedCase(),other=c?nearestSibling(c):null;
  if(!other){{$('compareBox').innerHTML='<span class="held">No same-action timing sibling exists for this case.</span>';return;}}
  const pathSame=c.realizedPathHash===other.realizedPathHash,endSame=c.endStateHash===other.endStateHash;
  $('compareBox').replaceChildren();
  const head=document.createElement('div');head.style.fontWeight='700';head.textContent=other.caseId;
  const detail=document.createElement('div');detail.style.marginTop='6px';
  const p=document.createElement('span');p.className=pathSame?'same':'different';p.textContent=pathSame?'same realized path':'different realized path';
  const sep=document.createTextNode(' · ');
  const e=document.createElement('span');e.className=endSame?'same':'different';e.textContent=endSame?'same endpoint':'different endpoint';
  const metrics=document.createElement('div');metrics.style.marginTop='6px';metrics.textContent=`depth ${{c.causalDepth}} → ${{other.causalDepth}} · transitions ${{c.transitionCount}} → ${{other.transitionCount}}`;
  detail.append(p,sep,e,metrics);$('compareBox').append(head,detail);
}}

$('search').addEventListener('input',renderCases);
$('shape').addEventListener('change',renderCases);
$('endpointFilter').addEventListener('change',()=>{{endpointPressed=$('endpointFilter').value;renderEndpoints();renderCases();}});
renderSummary();renderEndpoints();renderCases();renderSelected();
</script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a saved Causal Atlas and render a self-contained local Atlas Map."
    )
    parser.add_argument("atlas", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    atlas = _strict_load_json(args.atlas)
    rendered = render_atlas_map(atlas)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "atlasHash": atlas["atlasHash"],
                "authority": "DISPLAY_ONLY_NO_EXECUTION_NO_SELECTION_NO_CANON",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
