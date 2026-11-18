# -*- coding: utf-8 -*-
"""The Seestar Studio single-page web UI (HTML/CSS/JS), served by seestar_studio.py."""

STUDIO_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#05070e">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon.svg">
<link rel="apple-touch-icon" href="/icon.svg">
<title>Seestar Studio</title>
<style>
:root{
  --bg:#05070e; --bg2:#0a0f1c; --panel:rgba(18,25,42,.72); --panel2:rgba(12,18,32,.8);
  --line:rgba(90,120,170,.18); --txt:#e8eefb; --muted:#8ba0c4; --dim:#5f719a;
  --accent:#6ea8ff; --accent2:#9b7cff; --ok:#39d98a; --warn:#ffd166; --bad:#ff5d6c;
  --glow:0 0 24px rgba(110,168,255,.25);
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:radial-gradient(1200px 800px at 80% -10%,#141d33 0,#05070e 60%);
  color:var(--txt);font:14.5px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif;
  overflow:hidden}
a{color:var(--accent)}
#stars{position:fixed;inset:0;z-index:0;pointer-events:none}
.app{position:relative;z-index:1;display:grid;grid-template-columns:76px 1fr;grid-template-rows:56px 1fr;
  grid-template-areas:"brand top" "nav main";height:100vh;height:100dvh}
.top{grid-area:top;display:flex;align-items:center;gap:8px;padding:0 14px;overflow-x:auto;scrollbar-width:none;
  border-bottom:1px solid var(--line);backdrop-filter:blur(8px);background:rgba(8,12,22,.55)}
.brand{grid-area:brand;display:flex;align-items:center;justify-content:center;
  border-bottom:1px solid var(--line);border-right:1px solid var(--line);
  background:rgba(8,12,22,.55);backdrop-filter:blur(8px)}
.brand .logo{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;
  background:linear-gradient(135deg,var(--accent),var(--accent2));font-weight:800;
  box-shadow:var(--glow);color:#06101f}
.pill{font-size:12px;padding:4px 11px;border-radius:999px;border:1px solid var(--line);
  color:var(--muted);white-space:nowrap;display:inline-flex;gap:6px;align-items:center;flex:0 0 auto}
.pill.live{background:rgba(57,217,138,.14);border-color:rgba(57,217,138,.5);color:#8ff0c0}
.pill.dead{background:rgba(255,93,108,.14);border-color:rgba(255,93,108,.5);color:#ffb3bb}
.pill.warn{background:rgba(255,209,102,.12);border-color:rgba(255,209,102,.45);color:#f6dd9a}
.pill.demo{background:rgba(155,124,255,.18);border-color:rgba(155,124,255,.5);color:#d6cbff;font-weight:700}
button.pill{cursor:pointer;background:transparent;font:inherit;font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--bad)}
.dot.on{background:var(--ok);box-shadow:0 0 10px var(--ok);animation:pulse 2s infinite}
@keyframes pulse{50%{opacity:.45}}
.spacer{flex:1}
.nav{grid-area:nav;border-right:1px solid var(--line);background:rgba(8,12,22,.4);
  backdrop-filter:blur(8px);display:flex;flex-direction:column;align-items:stretch;padding:10px 8px;gap:4px;overflow:auto;scrollbar-width:none}
.nav button{appearance:none;border:0;background:transparent;color:var(--muted);cursor:pointer;
  border-radius:12px;padding:9px 6px;display:flex;flex-direction:column;align-items:center;gap:4px;
  font-size:10.5px;letter-spacing:.3px;transition:.15s;flex:0 0 auto}
.nav button svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:1.7}
.nav button:hover{color:var(--txt);background:rgba(110,168,255,.08)}
.nav button.sel{color:var(--txt);background:linear-gradient(135deg,rgba(110,168,255,.18),rgba(155,124,255,.14));
  box-shadow:inset 0 0 0 1px var(--line)}
.main{grid-area:main;overflow:auto;padding:18px;scrollbar-width:thin}
.view{display:none;animation:fade .25s ease}
.view.show{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.grid{display:grid;gap:14px}
.cols{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
.two{grid-template-columns:1fr 1fr}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;
  backdrop-filter:blur(6px);min-width:0}
.card h3{margin:0 0 10px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);font-weight:700}
.big{font-size:30px;font-weight:750;font-variant-numeric:tabular-nums;line-height:1.05}
.big.xl{font-size:40px}
.sub{color:var(--muted);font-size:12.5px;margin-top:4px}
.row{display:flex;justify-content:space-between;gap:10px;padding:4px 0;border-bottom:1px dashed rgba(90,120,170,.14);font-variant-numeric:tabular-nums}
.row:last-child{border-bottom:0}.row .k{color:var(--muted)}
.hero{display:grid;grid-template-columns:1.25fr .75fr;gap:14px}
.frame{position:relative;background:#000;border:1px solid var(--line);border-radius:16px;overflow:hidden;
  min-height:300px;display:grid;place-items:center;box-shadow:var(--glow)}
.frame img{width:100%;display:block;max-height:74vh;object-fit:contain;cursor:zoom-in}
.frame.stale img{filter:saturate(.55) brightness(.8)}
.frame .empty{color:var(--muted);padding:40px;text-align:center;font-size:13px}
.frame .ov{position:absolute;left:0;right:0;bottom:0;display:flex;justify-content:space-between;gap:8px;
  padding:10px 14px;background:linear-gradient(transparent,rgba(0,0,0,.8));font-size:12.5px;color:#cfe;pointer-events:none}
.frame .ovt{position:absolute;top:10px;left:14px;font-size:13px;font-weight:700;text-shadow:0 1px 6px #000;z-index:2}
.frame .stg{position:absolute;top:10px;right:12px;z-index:2}
.btn{appearance:none;cursor:pointer;border:1px solid var(--line);background:rgba(110,168,255,.1);
  color:var(--txt);border-radius:11px;padding:10px 14px;font:inherit;font-size:13px;font-weight:600;transition:.15s;
  display:inline-flex;align-items:center;gap:8px;justify-content:center;text-decoration:none;touch-action:manipulation;user-select:none}
.btn:hover{background:rgba(110,168,255,.2);border-color:rgba(110,168,255,.4)}
.btn:active{transform:translateY(1px)}
.btn.primary{background:linear-gradient(135deg,var(--accent),var(--accent2));border-color:transparent;color:#071326}
.btn.ok{background:rgba(57,217,138,.16);border-color:rgba(57,217,138,.4);color:#9ff0c6}
.btn.bad{background:rgba(255,93,108,.14);border-color:rgba(255,93,108,.4);color:#ffb3bb}
.btn.ghost{background:transparent}
.btn.sm{padding:6px 10px;font-size:12px;border-radius:9px}
.btn.on{border-color:var(--accent);background:rgba(110,168,255,.24)}
body.off .btn.ctl{opacity:.42}
.btnrow{display:flex;flex-wrap:wrap;gap:8px}
label.fld{display:block;margin:10px 0}
label.fld span{display:block;color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px}
input,select,textarea{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--txt);
  border-radius:10px;padding:10px 12px;font:inherit;font-size:13.5px}
input:focus,select:focus,textarea:focus{outline:1px solid var(--accent)}
input[type=range]{padding:0;accent-color:var(--accent)}
input[type=checkbox]{width:auto;accent-color:var(--accent)}
textarea{resize:vertical;font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.dpad{display:grid;grid-template-columns:repeat(3,68px);grid-template-rows:repeat(3,68px);gap:8px;justify-content:center;margin:6px auto}
.dpad .btn{width:68px;height:68px;border-radius:16px;font-size:20px;padding:0}
.dpad .btn.held{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#071326}
.dpad .mid{display:grid;place-items:center;color:var(--muted);font-size:10px;text-align:center}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.gal .it{border:1px solid var(--line);border-radius:12px;overflow:hidden;cursor:pointer;background:#000;position:relative}
.gal .it:hover{border-color:var(--accent)}
.gal .it img{width:100%;height:120px;object-fit:cover;display:block}
.gal .it .cap{padding:6px 8px;font-size:11px;color:var(--muted);background:var(--panel2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gal .it .cap b{color:var(--txt);font-weight:600}
.modal{position:fixed;inset:0;z-index:50;background:rgba(3,5,10,.93);display:none}
.modal.show{display:block}
.modal .stage{position:absolute;inset:0;overflow:hidden;display:grid;place-items:center;cursor:grab;touch-action:none}
.modal .stage img{max-width:96vw;max-height:92vh;transform-origin:center;user-select:none;-webkit-user-drag:none}
.modal .bar2{position:absolute;top:12px;right:14px;display:flex;gap:8px;z-index:2}
.dlg{position:fixed;inset:0;z-index:70;background:rgba(3,5,10,.7);display:none;place-items:center;padding:20px;backdrop-filter:blur(3px)}
.dlg.show{display:grid}
.dlg .box{background:#0e1526;border:1px solid var(--line);border-radius:16px;padding:20px;max-width:420px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.6)}
.dlg h4{margin:0 0 8px;font-size:16px}.dlg p{margin:0 0 16px;color:var(--muted)}
.console-out{background:#06090f;border:1px solid var(--line);border-radius:12px;padding:12px;
  font:12.5px/1.5 ui-monospace,Consolas,monospace;max-height:300px;min-height:120px;overflow:auto;white-space:pre-wrap;color:#bfe}
#log{background:#06090f;border:1px solid var(--line);border-radius:12px;padding:10px 12px;height:280px;overflow:auto;font:12px/1.5 ui-monospace,Consolas,monospace}
#log .l{display:flex;gap:10px}.l .t{color:#4b5a74;flex:0 0 60px}
.kd{flex:0 0 54px;text-transform:uppercase;font-size:10px;color:var(--muted)}
.kd.stack{color:var(--ok)}.kd.expose{color:var(--accent)}.kd.net{color:var(--warn)}
.kd.auth{color:var(--accent2)}.kd.cmd{color:#ffb86b}.kd.save{color:#7fe3e0}
#toasts{position:fixed;right:16px;bottom:16px;z-index:80;display:flex;flex-direction:column;gap:8px;max-width:360px}
.toast{background:#0f1729;border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:10px;padding:10px 14px;font-size:13px;box-shadow:0 10px 30px rgba(0,0,0,.4);animation:fade .2s}
.toast.ok{border-left-color:var(--ok)}.toast.bad{border-left-color:var(--bad)}.toast.warn{border-left-color:var(--warn)}
.hint{color:var(--muted);font-size:12px;margin-top:8px}
.badge{font-size:10.5px;padding:2px 8px;border-radius:999px;background:rgba(155,124,255,.16);color:#cbbcff;border:1px solid rgba(155,124,255,.3);text-transform:none;letter-spacing:0}
.alert{display:flex;gap:12px;align-items:flex-start;border-radius:14px;padding:12px 14px;margin-bottom:12px;font-size:13px;
  background:rgba(255,209,102,.08);border:1px solid rgba(255,209,102,.3);color:#f6dd9a}
.alert.bad{background:rgba(255,93,108,.1);border-color:rgba(255,93,108,.4);color:#ffc2c8}
.alert .ic{font-size:18px;line-height:1.2}.alert b{display:block;color:var(--txt)}
h2.vt{margin:0 0 14px;font-size:18px;font-weight:700;letter-spacing:.2px}
h2.vt small{color:var(--muted);font-weight:500;font-size:13px;margin-left:8px}
h4.sec{margin:20px 2px 10px;font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--muted)}
/* planner */
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.tools input,.tools select{width:auto;flex:1 1 150px;padding:8px 11px}
.plist{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px;max-height:62vh;overflow:auto;padding-right:2px}
.pit{display:grid;grid-template-columns:1fr auto;gap:2px 10px;padding:10px 12px;border:1px solid var(--line);border-radius:12px;
  background:var(--panel2);cursor:pointer;text-align:left;color:var(--txt);font:inherit}
.pit:hover,.pit.sel{border-color:var(--accent)}
.pit .n{font-weight:650}.pit .n small{color:var(--muted);font-weight:400;margin-left:6px}
.pit .a{font-variant-numeric:tabular-nums;font-weight:650;text-align:right}
.pit .m{grid-column:1/3;color:var(--muted);font-size:11.5px;display:flex;gap:8px;align-items:center;white-space:nowrap;overflow:hidden}
.pit .m span{flex:0 0 auto}.pit .m .altbar{flex:1 1 20px;min-width:12px}
.altbar{flex:1;height:4px;border-radius:2px;background:rgba(90,120,170,.18);overflow:hidden}
.altbar i{display:block;height:100%;background:var(--accent);border-radius:2px}
.pit.low{opacity:.55}
/* charts */
.chart{position:relative;height:170px}
.chart canvas{width:100%;height:100%;display:block}
.tip{position:fixed;z-index:90;pointer-events:none;background:#0f1729;border:1px solid var(--line);border-radius:8px;
  padding:5px 9px;font-size:12px;display:none;white-space:nowrap;font-variant-numeric:tabular-nums}
.tip b{color:var(--txt)}.tip span{color:var(--muted)}
.chead{display:flex;justify-content:space-between;align-items:baseline}
.chead .v{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}

/* switches, plan rows */
.tgl{display:flex;flex-direction:column}
.srow{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:7px 0;border-bottom:1px dashed rgba(90,120,170,.14);font-size:13px;cursor:pointer}
.srow:last-child{border-bottom:0}.srow.na{opacity:.4;cursor:not-allowed}
.sw{appearance:none;width:38px!important;height:22px;border-radius:999px;background:rgba(90,120,170,.3);border:0;padding:0;position:relative;cursor:pointer;flex:0 0 auto;transition:.15s}
.sw::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#cfd9ee;transition:.15s}
.sw:checked{background:var(--accent)}.sw:checked::after{left:19px;background:#fff}
body.off .sw{opacity:.4}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{appearance:none;font:inherit;font-size:12.5px;cursor:pointer;border:1px solid var(--line);background:var(--panel2);border-radius:10px;padding:7px 11px;color:var(--txt);display:inline-flex;align-items:center;gap:6px}
.chip:hover{border-color:var(--accent)}.chip small{color:var(--muted)}.chip.low{opacity:.5}
.prow{border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-bottom:8px;background:var(--panel2)}
.prow .ph{display:flex;gap:6px;align-items:center}.prow .ph input{flex:1;padding:6px 9px;font-weight:650}
.prow .pf{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;align-items:flex-end}
.prow .pf label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;display:flex;flex-direction:column;gap:4px}
.prow .pf input[type=time],.prow .pf input[type=number]{width:118px;padding:6px 9px}
.prow .pf label.ck{flex-direction:row;align-items:center;text-transform:none;font-size:12.5px;color:var(--txt);padding-bottom:7px}
#vid{width:100%;display:block;max-height:74vh;object-fit:contain}
.pip{position:absolute;right:10px;bottom:40px;width:30%;max-width:280px;border-radius:10px;border:1px solid rgba(140,170,220,.55);box-shadow:0 6px 22px rgba(0,0,0,.55);cursor:pointer;z-index:3;background:#000}
@media(max-width:900px){.hero,.two{grid-template-columns:1fr}}
@media(max-width:720px){
  .app{grid-template-columns:1fr;grid-template-rows:50px 1fr 62px;grid-template-areas:"top" "main" "nav"}
  .brand{display:none}
  .nav{flex-direction:row;border-right:0;border-top:1px solid var(--line);padding:4px 6px;overflow-x:auto;
    padding-bottom:max(4px,env(safe-area-inset-bottom))}
  .nav button{min-width:60px;padding:6px 4px}
  .main{padding:12px}
  .big.xl{font-size:32px}
  #toasts{bottom:74px;left:12px;right:12px;max-width:none}
  #host{display:none!important}
}
</style>
</head>
<body class="off">
<canvas id="stars"></canvas>
<div class="app">
  <div class="brand"><div class="logo">&#10022;</div></div>
  <div class="top">
    <span id="conn" class="pill"><span class="dot"></span>connecting</span>
    <span id="demo" class="pill demo" style="display:none" title="Simulated scope - safe to click anything">DEMO</span>
    <span id="modepill" class="pill">&mdash;</span>
    <span id="tgt" class="pill" style="display:none"></span>
    <span class="spacer"></span>
    <span id="batt" class="pill" style="display:none"></span>
    <span id="temp" class="pill" style="display:none"></span>
    <span id="host" class="pill" style="display:none"></span>
    <button id="bell" class="pill" onclick="toggleNotify()" title="Alerts: sound + desktop notification">&#128276; alerts</button>
  </div>

  <nav class="nav" id="nav"></nav>

  <main class="main">
    <div id="alerts"></div>

    <!-- LIVE -->
    <section class="view show" data-view="live">
      <div class="hero">
        <div>
          <div class="frame" id="frame">
            <div class="ovt" id="liveTgt"></div>
            <div class="stg" id="opsPills"></div>
            <img id="vid" style="display:none;cursor:default" alt="Live view">
            <img id="vidW" class="pip" style="display:none" alt="Wide-angle camera" title="Wide-angle camera - click to swap" onclick="swapCams()">
            <img id="live" style="display:none" alt="Live stacked image" onclick="openViewer('/api/image?kind=full&v='+Date.now(),'/api/image?kind=full&dl=1')">
            <div class="empty" id="liveEmpty">No live image yet &mdash; start a view or wait for the current stack.</div>
            <div class="ov"><span id="liveLabel"></span><span id="liveUpd"></span></div>
          </div>
          <div class="btnrow" style="margin-top:12px">
            <select id="viewMode" style="max-width:150px">
              <option value="star">Stargazing</option>
              <option value="sun">Solar</option>
              <option value="moon">Lunar</option>
              <option value="planet">Planetary</option>
              <option value="scenery">Scenery</option>
            </select>
            <button class="btn ok ctl" onclick="startView()">&#9205; Start view</button>
            <button class="btn primary ctl" id="bStack" onclick="startStack()">&#9733; Start stacking</button>
            <button class="btn ctl" id="bStopStack" style="display:none" onclick="confirmAct('Stop stacking?','The stack so far is saved on the scope. The live view stays on.','stop_stack',{})">Stop stacking</button>
            <button class="btn bad ctl" onclick="confirmAct('Stop everything?','Ends the current view (stacking, video or slew). The scope stays pointed where it is.','stop_view',{})">&#9209; Stop all</button>
          </div>
          <div class="btnrow" style="margin-top:8px">
            <button class="btn" id="bSnap" onclick="snapshot()" title="Save the current live-view frame to this PC">&#128247; Snapshot</button>
            <button class="btn ctl" id="bRec" onclick="toggleRec()" title="Record video on the scope (Solar / Lunar / Planetary / Scenery)">&#9210; Record video</button>
            <button class="btn" onclick="saveNow()" title="Copy the full-resolution stack to this PC's captures folder">&#128190; Save stack to PC</button>
            <a class="btn ghost" href="/api/image?kind=full&dl=1">Download &#8595;</a>
          </div>
        </div>
        <div class="grid" style="align-content:start">
          <div class="card"><h3>Frames stacked</h3><div class="big xl" id="c_stacked">&mdash;</div><div class="sub" id="c_dropped">dropped &mdash;</div></div>
          <div class="card"><h3>Integration</h3><div class="big" id="c_integ">&mdash;</div><div class="sub" id="c_integsub">&mdash;</div></div>
          <div class="card"><h3>Status</h3><div class="big" id="c_exp">&mdash;</div><div class="sub" id="c_expsub">&mdash;</div></div>
          <div class="card"><h3>Power</h3><div class="big" id="c_batt">&mdash;</div><div class="sub" id="c_battsub">&mdash;</div></div>
        </div>
      </div>
    </section>

    <!-- CAMERA -->
    <section class="view" data-view="imaging">
      <h2 class="vt">Camera <small>exposure, filters &amp; stacking</small></h2>
      <div class="grid cols">
        <div class="card">
          <h3>Sub-exposure (stacking)</h3>
          <select id="expSel">
            <option value="2000">2 s (expert)</option><option value="5000">5 s (expert)</option>
            <option value="10000" selected>10 s</option><option value="20000">20 s</option>
            <option value="30000">30 s</option><option value="60000">60 s</option>
          </select>
          <div class="sub">current <b id="e_cur">&mdash;</b></div>
          <button class="btn primary ctl" style="margin-top:10px;width:100%" onclick="act('set_exposure',{value:+$('expSel').value})">Apply exposure</button>
          <div class="hint">Takes effect on the next stack. Longer subs need good tracking (EQ mode helps).</div>
        </div>
        <div class="card">
          <h3>Gain</h3>
          <input type="range" id="gain" min="0" max="300" step="5" value="80" oninput="$('g_lbl').textContent=this.value">
          <div class="sub">value: <b id="g_lbl">80</b> &middot; current <b id="g_cur">&mdash;</b></div>
          <button class="btn primary ctl" style="margin-top:10px;width:100%" onclick="act('set_gain',{value:+$('gain').value})">Apply gain</button>
        </div>
        <div class="card">
          <h3>Filter</h3>
          <div class="btnrow">
            <button class="btn ctl" id="w1" onclick="act('wheel',{pos:1})">IR-cut (clear)</button>
            <button class="btn ctl" id="w2" onclick="act('wheel',{pos:2})">Light-pollution</button>
            <button class="btn ctl" id="w0" onclick="act('wheel',{pos:0})">Dark (closed)</button>
          </div>
          <div class="hint">In use: <b id="wheelCur">&mdash;</b>. The LP (dual-band) filter suits emission nebulae; use IR-cut for galaxies and clusters.</div>
        </div>
        <div class="card">
          <h3>Stacking options</h3>
          <div class="tgl" id="tgStack"></div>
        </div>
        <div class="card">
          <h3>Dithering</h3>
          <div class="grid two" style="gap:10px">
            <label class="fld" style="margin:0"><span>Shift (pixels)</span><input id="d_pix" type="number" min="0" max="200" value="50"></label>
            <label class="fld" style="margin:0"><span>Every N frames</span><input id="d_int" type="number" min="1" max="100" value="5"></label>
          </div>
          <button class="btn ctl" style="margin-top:10px;width:100%" onclick="act('setting',{key:'stack_dither',value:{pix:+$('d_pix').value,interval:+$('d_int').value,enable:true}})">Apply dithering</button>
          <div class="hint">Small random shifts between frames reduce walking noise.</div>
        </div>
        <div class="card">
          <h3>Live-view exposure <span class="badge">Sun / Moon / planets / scenery</span></h3>
          <div class="tgl"><label class="srow"><span>Manual exposure</span><input type="checkbox" class="sw ctl" data-k="manual_exp" onchange="setToggle(this)"></label></div>
          <div class="grid two" style="gap:10px;margin-top:8px">
            <label class="fld" style="margin:0"><span>Exposure (ms)</span><input id="isp_exp" type="number" min="0.03" max="1000" step="0.1"></label>
            <label class="fld" style="margin:0"><span>Gain</span><input id="isp_gain" type="number" min="0" max="400" step="1"></label>
          </div>
          <label class="fld"><span>Auto-exposure brightness: <b id="aeLbl">50</b>%</span><input type="range" id="ae" min="0" max="100" step="1" value="50" oninput="$('aeLbl').textContent=this.value"></label>
          <button class="btn ctl" style="width:100%" onclick="applyIsp()">Apply live-view exposure</button>
        </div>
        <div class="card">
          <h3>Calibration &amp; video</h3>
          <div class="btnrow">
            <button class="btn ctl" onclick="confirmAct('Capture dark frames?','The scope closes its filter and shoots a dark library. Imaging pauses while it runs.','dark_frame',{})">Create dark frames</button>
            <button class="btn ctl" onclick="act('dark_stop',{})">Stop darks</button>
          </div>
          <div class="grid two" style="gap:10px;margin-top:10px">
            <label class="fld" style="margin:0"><span>Time-lapse interval (s, 0 = off)</span><input id="rec_tl" type="number" min="0" max="3600" value="0"></label>
            <label class="fld" style="margin:0;display:flex;align-items:flex-end;gap:8px"><input type="checkbox" id="rec_raw"><span style="margin:0 0 10px">record RAW video</span></label>
          </div>
          <div class="hint">Used by the Record button on the Live tab. Recordings are stored on the scope.</div>
        </div>
      </div>
    </section>

    <!-- TARGET -->
    <section class="view" data-view="target">
      <h2 class="vt">Targets <small id="skyNow"></small></h2>
      <div class="grid two">
        <div class="card">
          <h3>Solar system</h3>
          <div class="chips" id="solar"></div>
          <h3 style="margin-top:16px">Deep sky <span class="badge" id="locBadge">set a location for altitudes</span></h3>
          <div class="tools">
            <input id="p_q" placeholder="Search M 42, Orion, galaxy..." oninput="renderPlanner()">
            <select id="p_type" onchange="renderPlanner()">
              <option value="">All types</option><option value="neb">Nebulae</option>
              <option value="gal">Galaxies</option><option value="clu">Clusters</option>
            </select>
            <select id="p_sort" onchange="renderPlanner()">
              <option value="alt">Highest now</option><option value="mag">Brightest</option><option value="name">Name</option>
            </select>
          </div>
          <div class="plist" id="plist"></div>
        </div>
        <div class="grid" style="align-content:start">
          <div class="card">
            <h3>GoTo</h3>
            <div class="grid two" style="gap:10px">
              <label class="fld" style="margin:0"><span>Target name</span><input id="t_name" placeholder="e.g. M 31"></label>
              <label class="fld" style="margin:0"><span>Mode</span><select id="t_mode" onchange="tgtInfo()">
                <option value="star">Deep sky (stack)</option><option value="sun">Sun</option><option value="moon">Moon</option><option value="planet">Planet</option></select></label>
              <label class="fld" style="margin:0"><span>RA (hours, J2000)</span><input id="t_ra" placeholder="0.712 or 00:42:44" oninput="tgtInfo()"></label>
              <label class="fld" style="margin:0"><span>Dec (degrees)</span><input id="t_dec" placeholder="41.269 or +41:16:09" oninput="tgtInfo()"></label>
            </div>
            <div class="hint" id="t_info">Pick a target from the lists or the sky map, or type coordinates.</div>
            <div class="grid two" style="gap:10px;margin-top:8px" id="frmRow">
              <label class="fld" style="margin:0"><span>Framing scale (1 = normal, up to 2 = mosaic)</span><input id="t_scale" type="number" min="1" max="2" step="0.1" value="1"></label>
              <label class="fld" style="margin:0"><span>Framing angle (&deg;)</span><input id="t_angle" type="number" min="0" max="360" step="1" value="0"></label>
            </div>
            <label class="fld" style="display:flex;align-items:center;gap:8px"><input type="checkbox" id="t_lp"><span style="margin:0">use light-pollution filter</span></label>
            <div class="btnrow">
              <button class="btn primary ctl" onclick="gotoManual()">&#128640; GoTo</button>
              <button class="btn ctl" onclick="slewOnly()" title="Move the mount without starting imaging">Slew only</button>
              <button class="btn ctl" id="bScan" style="display:none" onclick="act('scan_planet',{})" title="Let the scope search for and centre the Sun / Moon / planet">Auto-find</button>
              <button class="btn bad ctl" onclick="confirmAct('Stop the slew?','','stop_goto',{})">Stop slew</button>
            </div>
            <div class="btnrow" style="margin-top:8px">
              <button class="btn sm" onclick="planAdd()">+ Add to plan</button>
              <button class="btn sm" onclick="favAdd()">&#9734; Favourite</button>
            </div>
          </div>
          <div class="card">
            <h3>Sky now <span class="badge">tap an object</span></h3>
            <canvas id="sky" style="width:100%;max-width:360px;display:block;margin:0 auto;cursor:crosshair"></canvas>
            <div class="hint" style="text-align:center">Zenith at the centre, horizon at the edge. N up, E left. &#10753; = where the scope points.</div>
          </div>
          <div class="card">
            <h3>Favourites &amp; recent</h3>
            <div class="chips" id="favs"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- PLAN -->
    <section class="view" data-view="plan">
      <h2 class="vt">Plan <small>schedule a night of targets &mdash; runs on the scope itself</small></h2>
      <div class="grid two">
        <div class="card">
          <h3>Build a plan</h3>
          <label class="fld"><span>Plan name</span><input id="pl_name" value="Tonight" oninput="PLAN.name=this.value;planSave()"></label>
          <div id="pl_rows"></div>
          <div class="hint" id="pl_empty">No targets yet. Pick one on the Targets tab and press &ldquo;+ Add to plan&rdquo;.</div>
          <div class="tgl" id="tgPlan" style="margin-top:10px"></div>
          <div class="btnrow" style="margin-top:12px">
            <button class="btn primary ctl" onclick="planSend()">&#9205; Send to scope &amp; start</button>
            <button class="btn ghost" onclick="planClearLocal()">Clear list</button>
          </div>
          <div class="hint">Times are local clock times; anything earlier than the previous target counts as after midnight. The scope's clock is synced to this PC when you send. Once sent, the plan keeps running even if this PC is turned off.</div>
        </div>
        <div class="card" style="align-self:start">
          <h3>On the scope <span class="badge" id="pl_state">no plan</span></h3>
          <div id="pl_run"><div class="hint">No plan is loaded on the scope.</div></div>
          <div class="btnrow" style="margin-top:12px">
            <button class="btn bad ctl" onclick="confirmAct('Stop the running plan?','The current target stops and no further targets will run.','plan_stop',{})">Stop plan</button>
            <button class="btn ctl" onclick="confirmAct('Clear the plan from the scope?','Removes the stored plan. Images already taken are kept.','plan_clear',{})">Clear from scope</button>
          </div>
          <div class="btnrow" style="margin-top:8px">
            <button class="btn ghost" onclick="planFromScope()" title="Copies the targets, times, filters and mosaic settings of the plan on the scope into the builder on the left">&#8592; Copy this plan into the builder</button>
          </div>
        </div>
      </div>
    </section>

    <!-- FOCUS -->
    <section class="view" data-view="focus">
      <h2 class="vt">Focus</h2>
      <div class="grid cols">
        <div class="card">
          <h3>Autofocus</h3>
          <div class="btnrow">
            <button class="btn primary ctl" onclick="act('autofocus_start',{})">&#9211; Run autofocus</button>
            <button class="btn bad ctl" onclick="act('autofocus_stop',{})">Stop</button>
          </div>
          <div class="hint">Best run on a star field, and again after the temperature shifts a few degrees.</div>
        </div>
        <div class="card">
          <h3>Manual focuser</h3>
          <div class="btnrow" style="justify-content:center">
            <button class="btn ctl" onclick="act('focus_move',{step:-50})">&minus;50</button>
            <button class="btn ctl" onclick="act('focus_move',{step:-10})">&minus;10</button>
            <button class="btn ctl" onclick="act('focus_move',{step:-1})">&minus;1</button>
            <button class="btn ctl" onclick="act('focus_move',{step:1})">+1</button>
            <button class="btn ctl" onclick="act('focus_move',{step:10})">+10</button>
            <button class="btn ctl" onclick="act('focus_move',{step:50})">+50</button>
          </div>
          <div class="sub" style="text-align:center;margin-top:12px">position <span class="big" id="focPos" style="font-size:22px;margin-left:6px">&mdash;</span> <span style="color:var(--dim)">(1200 &ndash; 2600)</span></div>
          <div class="btnrow" style="margin-top:12px;justify-content:center">
            <input id="foc_to" type="number" min="1200" max="2600" placeholder="position" style="max-width:130px">
            <button class="btn ctl" onclick="focusTo()">Move to</button>
          </div>
        </div>
      </div>
    </section>

    <!-- MOUNT -->
    <section class="view" data-view="mount">
      <h2 class="vt">Mount <small>hold a direction to slew</small></h2>
      <div class="card" style="margin-bottom:14px">
        <h3>Where it is pointing <small style="font-weight:400;color:var(--muted)">drag to rotate &middot; scroll to zoom &middot; double-click to reset</small></h3>
        <canvas id="v3d" style="width:100%;display:block;touch-action:none;cursor:grab;border-radius:12px;background:radial-gradient(ellipse at 50% 30%,#101a33,#05070e 75%)"></canvas>
        <div id="v3dTxt" style="margin-top:10px;font-size:13.5px;line-height:1.5"></div>
      </div>
      <div class="card" style="margin-bottom:14px">
        <h3>Skyline <small style="font-weight:400;color:var(--muted)">what blocks your view, measured with the wide camera</small></h3>
        <div id="sk_txt" style="font-size:13.5px;line-height:1.5">No skyline measured yet.</div>
        <div id="sk_box" style="display:none;position:relative;margin-top:10px;border-radius:10px;overflow:hidden">
          <img id="sk_img" alt="Panorama of the horizon" style="width:100%;display:block">
          <canvas id="sk_cv" style="position:absolute;left:0;top:0;width:100%;height:100%"></canvas>
        </div>
        <div class="btnrow" style="margin-top:12px;align-items:center">
          <button class="btn primary ctl" id="sk_go" onclick="skyScan()">Scan the skyline</button>
          <button class="btn ctl" id="sk_arm" onclick="skyArm()" title="Starts by itself the next time the scope is idle during dawn or dusk twilight">Scan at next twilight</button>
          <button class="btn ghost" id="sk_disarm" style="display:none" onclick="skyDisarm()">Cancel the armed scan</button>
          <button class="btn bad" id="sk_stop" style="display:none" onclick="skyStop()">Stop scan</button>
          <select id="sk_max" style="max-width:190px" title="How far up the scan looks. Higher takes longer.">
            <option value="25">up to 25&deg; (quick)</option><option value="40" selected>up to 40&deg;</option><option value="55">up to 55&deg; (tall trees)</option></select>
          <button class="btn ghost" onclick="skyClear()">Forget</button>
        </div>
        <div class="hint">The yellow line is the detected skyline; it is also drawn in the 3D view above and used to warn when a planned target is behind it. The scan needs the scope idle (no view or plan running), and it never turns a full circle, to protect the power cable.</div>
      </div>
      <div class="grid cols">
        <div class="card" style="text-align:center">
          <h3>Nudge</h3>
          <div class="dpad" id="dpad">
            <div></div>
            <button class="btn ctl" data-ang="90" aria-label="Up">&#9650;</button>
            <div></div>
            <button class="btn ctl" data-ang="180" aria-label="Left">&#9664;</button>
            <div class="mid">speed<br><b id="spdLbl">500</b></div>
            <button class="btn ctl" data-ang="0" aria-label="Right">&#9654;</button>
            <div></div>
            <button class="btn ctl" data-ang="270" aria-label="Down">&#9660;</button>
            <div></div>
          </div>
          <input type="range" id="spd" min="100" max="1440" step="20" value="500" oninput="$('spdLbl').textContent=this.value" style="margin-top:12px">
          <div class="hint">Arrow keys work too while this tab is open.</div>
        </div>
        <div class="card">
          <h3>Position</h3>
          <div class="row"><span class="k">RA</span><span id="m_ra">&mdash;</span></div>
          <div class="row"><span class="k">Dec</span><span id="m_dec">&mdash;</span></div>
          <div class="row"><span class="k">Altitude / azimuth</span><span id="m_alt">&mdash;</span></div>
          <div class="row"><span class="k">Arm</span><span id="m_arm">&mdash;</span></div>
          <div class="row"><span class="k">Tracking</span><span id="m_track">&mdash;</span></div>
          <div class="btnrow" style="margin-top:12px">
            <button class="btn ctl" onclick="act('tracking',{on:true})">Tracking on</button>
            <button class="btn ctl" onclick="act('tracking',{on:false})">off</button>
          </div>
          <div class="btnrow" style="margin-top:8px">
            <button class="btn ctl" onclick="confirmAct('Open the arm?','Raises the arm from the parked position to the horizon.','open_arm',{})">Open arm</button>
            <button class="btn bad ctl" onclick="confirmAct('Park the scope?','Stops imaging and folds the arm back to its closed position.','park',{})">&#127968; Park</button>
          </div>
        </div>
        <div class="card">
          <h3>Plate solve &amp; sync</h3>
          <div class="btnrow">
            <button class="btn ctl" onclick="act('solve',{})">Plate solve now</button>
            <button class="btn ctl" onclick="syncMount()" title="Tell the mount it is pointing at the coordinates in the GoTo box">Sync to GoTo coords</button>
          </div>
          <div class="row" style="margin-top:10px"><span class="k">Solved centre</span><span id="m_solve">&mdash;</span></div>
          <div class="row"><span class="k">Field / rotation</span><span id="m_solve2">&mdash;</span></div>
        </div>
        <div class="card">
          <h3>Equatorial mode &amp; polar alignment</h3>
          <div class="row"><span class="k">Mount mode</span><span id="m_eq">&mdash;</span></div>
          <div class="row"><span class="k">Polar-align error</span><span id="m_pa">&mdash;</span></div>
          <div class="btnrow" style="margin-top:12px">
            <button class="btn ctl" onclick="confirmAct('Switch to EQ mode?','Only do this with the scope tilted on a wedge at your latitude. It parks the arm into the equatorial home position.','eq_mode',{on:true})">EQ mode</button>
            <button class="btn ctl" onclick="confirmAct('Switch to Alt-Az mode?','Parks the arm in the normal (level) position.','eq_mode',{on:false})">Alt-Az mode</button>
          </div>
          <div class="btnrow" style="margin-top:8px">
            <button class="btn ctl" onclick="confirmAct('Start polar alignment?','The scope slews to three points and plate-solves to measure the alignment error. Needs EQ mode and a clear sky.','polar_align',{})">Polar align</button>
            <button class="btn ctl" onclick="act('polar_align_stop',{})">Stop</button>
          </div>
          <div class="tgl" id="tgMount" style="margin-top:8px"></div>
        </div>
        <div class="card">
          <h3>Level &amp; compass</h3>
          <div style="display:flex;gap:16px;align-items:center">
            <canvas id="lvl" width="110" height="110" style="width:110px;height:110px;flex:0 0 auto"></canvas>
            <div style="flex:1">
              <div class="row"><span class="k">Tilt</span><span id="m_tilt">&mdash;</span></div>
              <div class="row"><span class="k">Compass</span><span id="m_comp">&mdash;</span></div>
            </div>
          </div>
          <div class="hint">Keep the bubble centred (under about 1&deg;) for accurate GoTo.</div>
        </div>
      </div>
    </section>

    <!-- ALBUMS -->
    <section class="view" data-view="albums">
      <h2 class="vt">Albums</h2>
      <h4 class="sec" style="margin-top:0">On the scope</h4>
      <div class="gal" id="gal"></div>
      <div class="hint" id="galEmpty" style="display:none">Nothing listed &mdash; the scope is offline or has no saved works.</div>
      <h4 class="sec">Saved on this PC <span class="badge" id="capInfo"></span></h4>
      <div class="gal" id="capGal"></div>
      <div class="hint" id="capEmpty" style="display:none">No saved stacks yet. While a session runs, the full-resolution stack is copied to this PC automatically &mdash; so the result survives even if the scope loses power.</div>
      <div class="hint" id="capDir"></div>
    </section>

    <!-- STATS -->
    <section class="view" data-view="stats">
      <h2 class="vt">Session stats
        <span class="btnrow" style="display:inline-flex;margin-left:10px;vertical-align:middle" id="rng">
          <button class="btn sm" data-h="1">1 h</button><button class="btn sm on" data-h="6">6 h</button><button class="btn sm" data-h="24">24 h</button>
        </span></h2>
      <div class="grid cols" style="margin-bottom:14px">
        <div class="card"><h3>Stack rate</h3><div class="big" id="k_rate">&mdash;</div><div class="sub">frames per hour</div></div>
        <div class="card"><h3>Frames kept</h3><div class="big" id="k_keep">&mdash;</div><div class="sub" id="k_keepsub">accepted vs dropped</div></div>
        <div class="card"><h3>Battery drain</h3><div class="big" id="k_drain">&mdash;</div><div class="sub" id="k_drainsub">% per hour</div></div>
        <div class="card"><h3>Saved to PC</h3><div class="big" id="k_saves">&mdash;</div><div class="sub" id="k_savesub">&mdash;</div></div>
      </div>
      <div class="grid cols" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">
        <div class="card"><div class="chead"><h3>Battery (%)</h3><span class="v" id="v_b">&mdash;</span></div><div class="chart"><canvas id="ch_b"></canvas></div></div>
        <div class="card"><div class="chead"><h3>Sensor temperature (&deg;C)</h3><span class="v" id="v_c">&mdash;</span></div><div class="chart"><canvas id="ch_c"></canvas></div></div>
        <div class="card"><div class="chead"><h3>Frames stacked</h3><span class="v" id="v_f">&mdash;</span></div><div class="chart"><canvas id="ch_f"></canvas></div></div>
      </div>
      <div class="hint">Sampled every 30 s while Studio runs; gaps mean the scope was offline.</div>
    </section>

    <!-- CONSOLE -->
    <section class="view" data-view="console">
      <h2 class="vt">Console <small>raw JSON-RPC &mdash; send any method the firmware supports</small></h2>
      <div class="grid two">
        <div class="card">
          <h3>Request</h3>
          <label class="fld"><span>method</span><input id="rpc_m" placeholder="get_device_state" list="rpcHist" autocomplete="off"></label>
          <datalist id="rpcHist"></datalist>
          <label class="fld"><span>params (JSON, optional)</span><textarea id="rpc_p" rows="4" placeholder='{"mode":"star"}'></textarea></label>
          <button class="btn primary" style="width:100%" onclick="sendRpc()">Send</button>
          <div class="hint">Read-only quick picks:
            <a href="#" onclick="qm('get_device_state');return false">device_state</a> &middot;
            <a href="#" onclick="qm('iscope_get_app_state');return false">app_state</a> &middot;
            <a href="#" onclick="qm('get_setting');return false">setting</a> &middot;
            <a href="#" onclick="qm('get_albums');return false">albums</a> &middot;
            <a href="#" onclick="qm('get_camera_info');return false">camera_info</a> &middot;
            <a href="#" onclick="qm('pi_get_time');return false">time</a> &middot;
            <a href="#" onclick="qm('get_user_location');return false">location</a></div>
        </div>
        <div class="card">
          <h3>Response <button class="btn sm ghost" style="float:right;margin-top:-6px" onclick="navigator.clipboard&&navigator.clipboard.writeText($('rpcOut').textContent)">copy</button></h3>
          <div class="console-out" id="rpcOut">&mdash;</div>
        </div>
      </div>
      <h4 class="sec">Event log
        <span class="btnrow" style="display:inline-flex;margin-left:10px" id="logf">
          <button class="btn sm on" data-k="">all</button><button class="btn sm" data-k="stack">stack</button>
          <button class="btn sm" data-k="cmd">commands</button><button class="btn sm" data-k="event">events</button><button class="btn sm" data-k="net">network</button></span></h4>
      <div id="log"></div>
    </section>

    <!-- SETTINGS -->
    <section class="view" data-view="settings">
      <h2 class="vt">Settings &amp; device</h2>
      <div class="grid cols">
        <div class="card">
          <h3>Device</h3>
          <div class="row"><span class="k">Model</span><span id="s_model">&mdash;</span></div>
          <div class="row"><span class="k">Firmware</span><span id="s_fw">&mdash;</span></div>
          <div class="row"><span class="k">Serial</span><span id="s_sn">&mdash;</span></div>
          <div class="row"><span class="k">Free storage</span><span id="s_disk">&mdash;</span></div>
          <div class="row"><span class="k">Wi-Fi</span><span id="s_wifi">&mdash;</span></div>
          <div class="row"><span class="k">Auth</span><span id="s_auth">&mdash;</span></div>
          <div class="row"><span class="k">Last seen</span><span id="s_seen">&mdash;</span></div>
        </div>
        <div class="card">
          <h3>Observing location</h3>
          <div class="grid two" style="gap:10px">
            <label class="fld" style="margin:0"><span>Latitude</span><input id="loc_lat" placeholder="39.74" inputmode="decimal"></label>
            <label class="fld" style="margin:0"><span>Longitude</span><input id="loc_lon" placeholder="-104.99" inputmode="decimal"></label>
          </div>
          <div class="btnrow" style="margin-top:10px">
            <button class="btn" onclick="saveLoc()">Save</button>
            <button class="btn ghost" onclick="geoLoc()">Use this device's location</button>
            <button class="btn ctl" onclick="pushLoc()" title="Store this location on the Seestar (needed for accurate GoTo)">Send to scope</button>
          </div>
          <div class="hint" id="locHint">Used in your browser to work out target altitudes.</div>
          <div class="row" style="margin-top:8px"><span class="k">On the scope</span><span id="s_sloc">&mdash;</span></div>
        </div>
        <div class="card">
          <h3>Clock, sound &amp; power saving</h3>
          <div class="btnrow">
            <button class="btn ctl" onclick="syncClock()" title="Set the scope's clock and time zone from this device">Sync scope clock</button>
            <button class="btn ctl" onclick="act('play_sound',{num:1})" title="Makes the scope beep so you can find it">Beep (find scope)</button>
          </div>
          <label class="fld"><span>Sound volume</span><select id="s_vol" class="ctl" onchange="act('setting',{key:'beep_volume',value:this.value})">
            <option value="close">Muted</option><option value="backyard">Backyard (quiet)</option><option value="indoor">Indoor</option><option value="outdoor">Outdoor (loud)</option></select></label>
          <div class="tgl" id="tgDev"></div>
        </div>
        <div class="card">
          <h3>Alerts &amp; auto-save</h3>
          <div class="row"><span class="k">Alert sound / notifications</span><span id="s_notify">off</span></div>
          <div class="row"><span class="k">Auto-save stack to PC</span><span id="s_auto">&mdash;</span></div>
          <div class="row"><span class="k">Last save</span><span id="s_lastcap">&mdash;</span></div>
          <div class="btnrow" style="margin-top:10px"><button class="btn" onclick="toggleNotify()">Toggle alerts</button>
            <button class="btn ghost" onclick="beep();toast('Test alert','warn')">Test</button></div>
          <div class="hint">Alerts fire for: scope offline, low battery (20 / 10 / 5%), stalled stacking, storage nearly full.</div>
        </div>
        <div class="card">
          <h3>Dew heater</h3>
          <input type="range" id="dew" min="0" max="100" step="5" value="90" oninput="$('dewLbl').textContent=this.value+'%'">
          <div class="sub">power: <b id="dewLbl">90%</b> &middot; current <b id="dewCur">&mdash;</b></div>
          <div class="btnrow" style="margin-top:10px">
            <button class="btn ok ctl" onclick="act('dew_heater',{on:true,value:+$('dew').value})">Heater ON</button>
            <button class="btn ctl" onclick="act('dew_heater',{on:false,value:0})">OFF</button>
          </div>
        </div>
        <div class="card">
          <h3>Power</h3>
          <div class="btnrow">
            <button class="btn bad ctl" onclick="confirmAct('Reboot the Seestar?','It will disconnect for about a minute and any running session ends.','reboot',{})">Reboot</button>
            <button class="btn bad ctl" onclick="shutdownScope()">Shut down</button>
          </div>
          <div class="hint">Shut down parks the arm first. Not included here on purpose: firmware updates, Wi-Fi setup and storage formatting &mdash; use the official app for those.</div>
        </div>
        <div class="card">
          <h3>Shortcuts</h3>
          <div class="row"><span class="k">1 &ndash; 9, 0</span><span>switch tab</span></div>
          <div class="row"><span class="k">Arrow keys</span><span>nudge (Mount tab)</span></div>
          <div class="row"><span class="k">Esc</span><span>close viewer / dialog</span></div>
          <div class="hint">On a phone: use your browser's &ldquo;Add to Home screen&rdquo; for an app-like icon.</div>
        </div>
      </div>
    </section>
  </main>
</div>

<div class="modal" id="modal">
  <div class="bar2"><a class="btn sm" id="viewDl" href="#">Download &#8595;</a><button class="btn sm bad" id="viewDel" style="display:none">Delete from scope</button><button class="btn sm" onclick="zoomBy(1.5)">+</button><button class="btn sm" onclick="zoomBy(1/1.5)">&minus;</button><button class="btn sm" onclick="closeViewer()">Close &times;</button></div>
  <div class="stage" id="vstage"><img id="modalImg" alt="Full-resolution image"></div>
</div>
<div class="dlg" id="dlg"><div class="box"><h4 id="dlgT"></h4><p id="dlgM"></p>
  <div class="btnrow" style="justify-content:flex-end"><button class="btn ghost" id="dlgNo">Cancel</button><button class="btn primary" id="dlgYes">Confirm</button></div></div></div>
<div class="tip" id="tip"></div>
<div id="toasts"></div>

<script>
const $=id=>document.getElementById(id);
let S=null;                       // latest /api/state
// ---------- starfield ----------
(function(){
  const c=$('stars'),x=c.getContext('2d');let w,h,st=[];
  function rs(){w=c.width=innerWidth;h=c.height=innerHeight;st=[];const n=Math.min(220,(w*h)/9000);
    for(let i=0;i<n;i++)st.push({x:Math.random()*w,y:Math.random()*h,r:Math.random()*1.3+.2,t:Math.random()*6.28,s:Math.random()*.02+.004});}
  function draw(){if(!document.hidden){x.clearRect(0,0,w,h);for(const s of st){s.t+=s.s;const a=.35+Math.sin(s.t)*.35;
    x.globalAlpha=a;x.fillStyle=s.r>1.1?'#bcd0ff':'#ffffff';x.beginPath();x.arc(s.x,s.y,s.r,0,6.28);x.fill();}
    x.globalAlpha=1;}setTimeout(()=>requestAnimationFrame(draw),60);}
  addEventListener('resize',rs);rs();draw();
})();

// ---------- nav ----------
const NAV=[["live","Live",'<path d="M3 12a9 9 0 1 0 18 0 9 9 0 1 0-18 0"/><circle cx="12" cy="12" r="3"/>'],
["imaging","Camera",'<rect x="3" y="7" width="18" height="13" rx="2"/><circle cx="12" cy="13.5" r="3.5"/><path d="M8 7l1.5-2h5L16 7"/>'],
["target","Targets",'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>'],
["plan","Plan",'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M4 10h16M8 14h3M8 17h6"/>'],
["focus","Focus",'<circle cx="12" cy="12" r="7"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/>'],
["mount","Mount",'<path d="M12 3v8M5 21l7-10 7 10"/><circle cx="12" cy="11" r="1.5"/>'],
["albums","Albums",'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 15l5-4 4 3 3-2 6 5"/><circle cx="8" cy="9" r="1.5"/>'],
["stats","Stats",'<path d="M4 20V4M4 20h16M8 16l4-5 3 3 5-7"/>'],
["console","Console",'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>'],
["settings","Settings",'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>']];
let curView='live';
NAV.forEach(([id,label,svg],i)=>{const b=document.createElement('button');b.dataset.v=id;b.title=label+' ('+((i+1)%10)+')';
  b.innerHTML='<svg viewBox="0 0 24 24">'+svg+'</svg>'+label;b.onclick=()=>sel(id);$('nav').appendChild(b);});
function sel(id){curView=id;document.querySelectorAll('.view').forEach(v=>v.classList.toggle('show',v.dataset.view===id));
  document.querySelectorAll('.nav button').forEach(b=>b.classList.toggle('sel',b.dataset.v===id));
  try{localStorage.setItem('tab',id);}catch(e){}
  if(id==='albums')loadAlbums();if(id==='stats')loadHistory();if(id==='target'){renderPlanner();requestAnimationFrame(drawSky);}if(id==='plan'){renderPlan();if(S)renderRun();}}

// ---------- helpers ----------
function toast(msg,cls){const t=document.createElement('div');t.className='toast '+(cls||'');t.textContent=msg;
  $('toasts').appendChild(t);setTimeout(()=>t.remove(),4500);}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function lsGet(k,d){try{const v=JSON.parse(localStorage.getItem(k));return v==null?d:v;}catch(e){return d;}}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  return {status:r.status,data:await r.json().catch(()=>({}))};}
const NICE={start_view:'Start view',stop_view:'Stop',stop_stack:'Stop stacking',start_stack:'Start stacking',goto:'GoTo',slew:'Slew',sync:'Sync',
  stop_goto:'Stop slew',scan_planet:'Auto-find',autofocus_start:'Autofocus',autofocus_stop:'Stop autofocus',focus_move:'Focuser',focus_to:'Focuser',
  mount_move:'Mount move',park:'Park',eq_mode:'Mount mode',open_arm:'Open arm',tracking:'Tracking',set_gain:'Gain',set_exposure:'Exposure',
  lp_filter:'LP filter',wheel:'Filter',setting:'Setting',dew_heater:'Dew heater',dark_frame:'Dark frames',dark_stop:'Stop darks',solve:'Plate solve',
  polar_align:'Polar alignment',polar_align_stop:'Stop polar alignment',record_start:'Recording',record_stop:'Stop recording',
  set_location:'Location',sync_time:'Clock sync',play_sound:'Beep',plan_start:'Plan',plan_stop:'Stop plan',plan_clear:'Clear plan',
  delete_image:'Delete',reboot:'Reboot',shutdown:'Shut down'};
async function act(action,params,quiet){
  const name=NICE[action]||action;
  if(!S||!S.connected){if(!quiet)toast('Scope is offline - "'+name+'" was not sent','bad');return false;}
  try{const {data}=await post('/api/action',{action,params});
    if(data.ok){if(!quiet)toast('\u2713 '+name+' sent','ok');setTimeout(tick,500);return true;}
    toast('\u2717 '+name+': '+(data.error||('scope replied code '+data.code+(data.reply&&data.reply.error?' ('+data.reply.error+')':''))),'bad');
  }catch(e){toast('\u2717 '+name+': '+e,'bad');}
  return false;
}
function ask(title,msg,yes){return new Promise(res=>{$('dlgT').textContent=title;$('dlgM').textContent=msg||'';
  $('dlgYes').textContent=yes||'Confirm';$('dlg').classList.add('show');
  const done=v=>{$('dlg').classList.remove('show');$('dlgYes').onclick=$('dlgNo').onclick=null;res(v);};
  $('dlgYes').onclick=()=>done(true);$('dlgNo').onclick=()=>done(false);$('dlg').onclick=e=>{if(e.target===$('dlg'))done(false);};});}
async function confirmAct(title,msg,action,params){if(await ask(title,msg))act(action,params);}
function isStacking(){return !!(S&&S.connected&&S.view&&S.view.stage==='Stack');}
function planRunning(){return !!(S&&S.connected&&S.plan&&S.plan.state==='working');}
async function startView(){const m=$('viewMode').value;
  if(planRunning()&&!(await ask('A plan is running','Starting a view by hand interrupts the plan on the scope.','Start anyway')))return;
  if(isStacking()&&!(await ask('Start a new view?','A stacking session is running. Starting a new view ends it (the stack so far is kept on the scope).')))return;
  if(m==='sun'&&!(await ask('Solar mode','Make sure the solar filter is fitted before pointing at the Sun.','Filter is on')))return;
  act('start_view',{mode:m});}
async function startStack(){if(!S||!S.view||S.target.mode!=='star'){toast('Open Stargazing mode or GoTo a target first','bad');return;}
  act('start_stack',{restart:true});}
async function saveNow(){if(!S||!S.connected){toast('Scope is offline - nothing new to save','bad');return;}
  toast('Fetching full-resolution stack\u2026');const {data}=await post('/api/save_now',{});
  toast(data.ok?('\u2713 Saved '+data.name):('\u2717 '+(data.error||'save failed')),data.ok?'ok':'bad');}
async function snapshot(){if(!vidOn){saveNow();return;}const {data}=await post('/api/snapshot',{});
  toast(data.ok?('\u2713 Saved '+data.name):('\u2717 '+(data.error||'snapshot failed')),data.ok?'ok':'bad');}
let recOn=false;
async function toggleRec(){if(!recOn){if(!S||!S.view||S.view.stage!=='RTSP'){toast('Video recording works in Solar, Lunar, Planetary and Scenery modes','bad');return;}
    if(await act('record_start',{raw:$('rec_raw').checked,timelapse:+$('rec_tl').value||0}))recOn=true;}
  else{if(await act('record_stop',{}))recOn=false;}
  $('bRec').innerHTML=recOn?'&#9209; Stop recording':'&#9210; Record video';$('bRec').classList.toggle('bad',recOn);}
function applyIsp(){const e=parseFloat($('isp_exp').value),g=parseFloat($('isp_gain').value);
  act('setting',{key:'ae_bri_percent',value:+$('ae').value},true);
  if(isFinite(e))act('setting',{key:'isp_exp_ms',value:e},true);
  if(isFinite(g))act('setting',{key:'isp_gain',value:g},true);toast('\u2713 Live-view exposure sent','ok');}
function focusTo(){const v=parseInt($('foc_to').value,10);if(!(v>=1200&&v<=2600)){toast('Enter a position from 1200 to 2600','bad');return;}act('focus_to',{pos:v});}
function pushLoc(){const lat=parseFloat($('loc_lat').value),lon=parseFloat($('loc_lon').value);
  if(!isFinite(lat)||!isFinite(lon)){toast('Enter a latitude and longitude first','bad');return;}
  confirmAct('Set the location on the scope?','Stores '+lat.toFixed(3)+'\u00b0, '+lon.toFixed(3)+'\u00b0 on the Seestar. It uses this for GoTo.','set_location',{lat,lon});}
function tzName(){try{return Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC';}catch(e){return 'UTC';}}
function syncClock(){act('sync_time',{tz:tzName()});}
async function shutdownScope(){if(!(await ask('Shut down the Seestar?','The arm is parked first, then the scope powers off. You will need to press its power button to turn it back on.','Shut down')))return;
  if(await act('park',{},true)){toast('Parking, then shutting down\u2026');setTimeout(()=>act('shutdown',{}),9000);}}
// settings toggles
function getPath(o,path){return path.split('.').reduce((a,k)=>a==null?a:a[k],o);}
const TG={tgStack:[['auto_af','Autofocus after GoTo'],['stack_after_goto','Start stacking automatically after GoTo'],['frame_calib','Frame calibration'],
  ['stack_dither.enable','Dithering'],['stack.save_discrete_ok_frame','Save good sub-frames'],['stack.save_discrete_frame','Save all sub-frames (incl. rejected)'],
  ['stack.dbe','Background gradient removal'],['stack.star_correction','Star correction'],['stack.airplane_line_removal','Remove aeroplane / satellite trails'],
  ['stack.drizzle2x','4K drizzle (2\u00d7)'],['enable_dark_library','Temperature-matched darks'],['expert_mode','Expert mode (2 s and 5 s subs)'],['wide_cam','Use the wide-angle camera']],
 tgPlan:[['plan_target_af','Autofocus before each target'],['viewplan_gohome','Park when the plan ends']],
 tgMount:[['auto_3ppa_calib','Automatic 3-point calibration']],
 tgDev:[['auto_power_off','Auto power-off when idle']]};
for(const id in TG)$(id).innerHTML=TG[id].map(([k,l])=>'<label class="srow"><span>'+l+'</span><input type="checkbox" class="sw ctl" data-k="'+k+'" onchange="setToggle(this)"></label>').join('');
function setToggle(el){const [top,sub]=el.dataset.k.split('.'),v=el.checked;el.dataset.hold=Date.now();
  act('setting',{key:top,value:sub?{[sub]:v}:v}).then(ok=>{if(!ok){el.checked=!v;el.dataset.hold=0;}});}
function syncToggles(){const st=(S&&S.settings)||{};document.querySelectorAll('.sw[data-k]').forEach(el=>{if(Date.now()-(+el.dataset.hold||0)<7000)return;
  const v=getPath(st,el.dataset.k),row=el.closest('.srow');el.disabled=v===undefined;row.classList.toggle('na',v===undefined);
  row.title=v===undefined?'Not reported by the scope (offline, or not on this firmware)':'';if(v!==undefined)el.checked=!!v;});}
function fill(id,v){const e=$(id);if(e&&document.activeElement!==e&&v!=null&&!e.dataset.t){e.value=v;}}

// ---------- coordinates ----------
function parseCoord(v){v=String(v).trim();if(!v)return NaN;
  if(/[:hd°m' ]/.test(v)){const neg=/^-/.test(v);const p=v.replace(/^[+-]/,'').split(/[^\d.]+/).filter(Boolean).map(Number);
    if(!p.length||p.some(isNaN))return NaN;const x=p[0]+(p[1]||0)/60+(p[2]||0)/3600;return neg?-x:x;}
  return parseFloat(v);}
function getLoc(){try{const l=JSON.parse(localStorage.getItem('loc')||'null');if(l&&isFinite(l.lat)&&isFinite(l.lon))return {lat:l.lat,lon:l.lon,src:'saved'};}catch(e){}
  if(S&&S.location&&S.location.lat!=null&&S.location.lon!=null)return {lat:S.location.lat,lon:S.location.lon,src:'scope'};return null;}
function saveLoc(){const lat=parseFloat($('loc_lat').value),lon=parseFloat($('loc_lon').value);
  if(!isFinite(lat)||!isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180){toast('Enter a valid latitude and longitude','bad');return;}
  localStorage.setItem('loc',JSON.stringify({lat,lon}));toast('Location saved','ok');showLoc();renderPlanner();}
function geoLoc(){if(!navigator.geolocation){toast('Location is not available in this browser','bad');return;}
  navigator.geolocation.getCurrentPosition(p=>{$('loc_lat').value=p.coords.latitude.toFixed(3);$('loc_lon').value=p.coords.longitude.toFixed(3);saveLoc();},
    ()=>toast('Could not get location (browsers only allow it on localhost/https) - type it in instead','bad'));}
let locShown=false;
function showLoc(){const l=getLoc();if(l&&(!locShown||document.activeElement.tagName!=='INPUT')){if(!locShown){$('loc_lat').value=l.lat;$('loc_lon').value=l.lon;locShown=true;}
  $('locHint').textContent=(l.src==='scope'?'Using the location stored on the scope. ':'')+'Used only in your browser to work out target altitudes.';}}
const R=Math.PI/180;
function lstH(d,lon){const jd=d/86400000+2440587.5,t=(jd-2451545)/36525;
  let g=280.46061837+360.98564736629*(jd-2451545)+0.000387933*t*t+lon;return (((g%360)+360)%360)/15;}
function altOf(ra,dec,loc,d){const ha=(lstH(d||Date.now(),loc.lon)-ra)*15*R;
  return Math.asin(Math.sin(dec*R)*Math.sin(loc.lat*R)+Math.cos(dec*R)*Math.cos(loc.lat*R)*Math.cos(ha))/R;}
function sunAlt(loc){const n=Date.now()/86400000+2440587.5-2451545,L=(280.46+0.9856474*n)%360,g=(357.528+0.9856003*n)*R,
  lam=(L+1.915*Math.sin(g)+0.02*Math.sin(2*g))*R,e=23.439*R;
  let ra=Math.atan2(Math.cos(e)*Math.sin(lam),Math.cos(lam))/R/15;if(ra<0)ra+=24;return altOf(ra,Math.asin(Math.sin(e)*Math.sin(lam))/R,loc);}
function transit(ra,loc){let dh=ra-lstH(Date.now(),loc.lon);dh=((dh+12)%24+24)%24-12;return new Date(Date.now()+dh*0.99727*3600000);}
const hm=d=>d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});

// ---------- solar system (low-precision ephemeris; the scope plate-solves / auto-finds) ----------
const EL={Mercury:[0.38709927,0.20563593,7.00497902,252.2503235,77.45779628,48.33076593,0.00000037,0.00001906,-0.00594749,149472.67411175,0.16047689,-0.12534081],
Venus:[0.72333566,0.00677672,3.39467605,181.9790995,131.60246718,76.67984255,0.0000039,-0.00004107,-0.0007889,58517.81538729,0.00268329,-0.27769418],
Earth:[1.00000261,0.01671123,-0.00001531,100.46457166,102.93768193,0,0.00000562,-0.00004392,-0.01294668,35999.37244981,0.32327364,0],
Mars:[1.52371034,0.0933941,1.84969142,-4.55343205,-23.94362959,49.55953891,0.00001847,0.00007882,-0.00813131,19140.30268499,0.44441088,-0.29257343],
Jupiter:[5.202887,0.04838624,1.30439695,34.39644051,14.72847983,100.47390909,-0.00011607,-0.00013253,-0.00183714,3034.74612775,0.21252668,0.20469106],
Saturn:[9.53667594,0.05386179,2.48599187,49.95424423,92.59887831,113.66242448,-0.0012506,-0.00050991,0.00193609,1222.49362201,-0.41897216,-0.28867794],
Uranus:[19.18916464,0.04725744,0.77263783,313.23810451,170.9542763,74.01692503,-0.00196176,-0.00004397,-0.00242939,428.48202785,0.40805281,0.04240589],
Neptune:[30.06992276,0.00859048,1.77004347,-55.12002969,44.96476227,131.78422574,0.00026291,0.00005105,0.00035372,218.45945325,-0.32241464,-0.00508664]};
function helio(name,T){const e=EL[name],a=e[0]+e[6]*T,ec=e[1]+e[7]*T,I=(e[2]+e[8]*T)*R,L=e[3]+e[9]*T,lp=e[4]+e[10]*T,ln=e[5]+e[11]*T;
  const w=(lp-ln)*R,O=ln*R;let M=((L-lp)%360+540)%360-180;M*=R;let E=M;for(let i=0;i<8;i++)E=M+ec*Math.sin(E);
  const xp=a*(Math.cos(E)-ec),yp=a*Math.sqrt(1-ec*ec)*Math.sin(E),cw=Math.cos(w),sw=Math.sin(w),cO=Math.cos(O),sO=Math.sin(O),cI=Math.cos(I),sI=Math.sin(I);
  return [(cw*cO-sw*sO*cI)*xp+(-sw*cO-cw*sO*cI)*yp,(cw*sO+sw*cO*cI)*xp+(-sw*sO+cw*cO*cI)*yp,sw*sI*xp+cw*sI*yp];}
function ecl2equ(x,y,z){const e=23.43928*R,ye=y*Math.cos(e)-z*Math.sin(e),ze=y*Math.sin(e)+z*Math.cos(e);
  let ra=Math.atan2(ye,x)/R/15;if(ra<0)ra+=24;return {ra,dec:Math.atan2(ze,Math.hypot(x,ye))/R};}
function bodyPos(name,d){const T=((d||Date.now())/86400000+2440587.5-2451545)/36525;
  if(name==='Moon'){const s=x=>Math.sin(x*R),lam=(218.32+481267.881*T+6.29*s(135+477198.87*T)-1.27*s(259.3-413335.36*T)+0.66*s(235.7+890534.22*T)+0.21*s(269.9+954397.74*T)-0.19*s(357.5+35999.05*T)-0.11*s(186.5+966404.03*T))*R,
      bet=(5.13*s(93.3+483202.02*T)+0.28*s(228.2+960400.89*T)-0.28*s(318.3+6003.15*T)-0.17*s(217.6-407332.21*T))*R;
    return ecl2equ(Math.cos(bet)*Math.cos(lam),Math.cos(bet)*Math.sin(lam),Math.sin(bet));}
  const E=helio('Earth',T);if(name==='Sun')return ecl2equ(-E[0],-E[1],-E[2]);
  const P=helio(name,T);return ecl2equ(P[0]-E[0],P[1]-E[1],P[2]-E[2]);}
const BODIES=[['Sun','sun','\u2609'],['Moon','moon','\u263d'],['Mercury','planet','\u263f'],['Venus','planet','\u2640'],['Mars','planet','\u2642'],
  ['Jupiter','planet','\u2643'],['Saturn','planet','\u2644'],['Uranus','planet','\u2645'],['Neptune','planet','\u2646']];
function renderSolar(){const loc=getLoc();$('solar').innerHTML=BODIES.map(([n,m,sym])=>{const p=bodyPos(n),a=loc?altOf(p.ra,p.dec,loc):null;
  return '<button class="chip'+(a!=null&&a<5?' low':'')+'" onclick="pickBody(\''+n+'\')">'+sym+' '+n+(a!=null?'<small>'+(a>=0?a.toFixed(0)+'\u00b0':'set')+'</small>':'')+'</button>';}).join('');}
function pickBody(n){const b=BODIES.find(x=>x[0]===n),p=bodyPos(n);$('t_name').value=n;$('t_ra').value=p.ra.toFixed(4);$('t_dec').value=p.dec.toFixed(3);
  $('t_mode').value=b[1];$('t_lp').checked=false;tgtInfo();renderPlanner();}

// ---------- planner catalogue: [name, RA h, Dec deg, common name, type, mag] ----------
const CAT=[["M 31",0.712,41.27,"Andromeda Galaxy","gal",3.4],["M 33",1.564,30.66,"Triangulum Galaxy","gal",5.7],["M 42",5.588,-5.39,"Orion Nebula","neb",4.0],
["M 45",3.790,24.12,"Pleiades","clu",1.6],["M 1",5.575,22.02,"Crab Nebula","neb",8.4],["M 13",16.695,36.46,"Hercules Cluster","clu",5.8],
["M 51",13.498,47.20,"Whirlpool Galaxy","gal",8.4],["M 81",9.926,69.07,"Bode's Galaxy","gal",6.9],["M 82",9.931,69.68,"Cigar Galaxy","gal",8.4],
["M 101",14.054,54.35,"Pinwheel Galaxy","gal",7.9],["M 27",19.994,22.72,"Dumbbell Nebula","neb",7.5],["M 57",18.893,33.03,"Ring Nebula","neb",8.8],
["M 8",18.063,-24.38,"Lagoon Nebula","neb",6.0],["M 20",18.043,-23.03,"Trifid Nebula","neb",6.3],["M 16",18.313,-13.78,"Eagle Nebula","neb",6.0],
["M 17",18.346,-16.18,"Omega Nebula","neb",6.0],["M 104",12.666,-11.62,"Sombrero Galaxy","gal",8.0],["M 3",13.703,28.38,"Globular","clu",6.2],
["M 5",15.310,2.08,"Globular","clu",5.6],["M 15",21.500,12.17,"Globular","clu",6.2],["M 22",18.607,-23.90,"Globular","clu",5.1],
["M 92",17.285,43.14,"Globular","clu",6.4],["M 2",21.558,-0.82,"Globular","clu",6.5],["M 4",16.393,-26.53,"Globular","clu",5.6],
["M 11",18.851,-6.27,"Wild Duck Cluster","clu",6.3],["M 35",6.148,24.33,"Open cluster","clu",5.3],["M 37",5.873,32.55,"Open cluster","clu",6.2],
["M 44",8.667,19.98,"Beehive Cluster","clu",3.7],["M 52",23.413,61.59,"Open cluster","clu",7.3],["M 63",13.264,42.03,"Sunflower Galaxy","gal",8.6],
["M 64",12.945,21.68,"Black Eye Galaxy","gal",8.5],["M 65",11.315,13.09,"Leo Triplet","gal",9.3],["M 66",11.337,12.99,"Leo Triplet","gal",8.9],
["M 74",1.611,15.78,"Phantom Galaxy","gal",9.4],["M 76",1.705,51.58,"Little Dumbbell","neb",10.1],["M 78",5.779,0.05,"Reflection nebula","neb",8.3],
["M 83",13.617,-29.87,"Southern Pinwheel","gal",7.5],["M 94",12.848,41.12,"Croc's Eye Galaxy","gal",8.2],["M 97",11.247,55.02,"Owl Nebula","neb",9.9],
["M 106",12.316,47.30,"Galaxy","gal",8.4],["NGC 253",0.793,-25.29,"Sculptor Galaxy","gal",7.1],["NGC 281",0.880,56.62,"Pacman Nebula","neb",7.4],
["NGC 869",2.317,57.13,"Double Cluster","clu",4.3],["NGC 891",2.376,42.35,"Edge-on galaxy","gal",9.9],["IC 1805",2.545,61.45,"Heart Nebula","neb",6.5],
["IC 1848",2.855,60.42,"Soul Nebula","neb",6.5],["NGC 1499",4.050,36.42,"California Nebula","neb",6.0],["IC 405",5.273,34.27,"Flaming Star","neb",6.0],
["IC 410",5.377,33.52,"Tadpoles Nebula","neb",7.5],["NGC 1977",5.588,-4.85,"Running Man","neb",7.0],["IC 434",5.683,-2.46,"Horsehead Nebula","neb",6.8],
["NGC 2024",5.698,-1.85,"Flame Nebula","neb",7.2],["IC 443",6.283,22.52,"Jellyfish Nebula","neb",12.0],["NGC 2237",6.533,4.95,"Rosette Nebula","neb",6.0],
["NGC 2264",6.683,9.88,"Cone / Christmas Tree","neb",3.9],["NGC 2359",7.310,-13.22,"Thor's Helmet","neb",11.5],["NGC 2392",7.486,20.91,"Eskimo Nebula","neb",9.2],
["NGC 2903",9.536,21.50,"Galaxy","gal",9.0],["NGC 3628",11.338,13.59,"Hamburger Galaxy","gal",9.5],["NGC 4565",12.606,25.99,"Needle Galaxy","gal",9.6],
["NGC 4631",12.703,32.54,"Whale Galaxy","gal",9.2],["NGC 5128",13.424,-43.02,"Centaurus A","gal",6.8],["NGC 5139",13.447,-47.48,"Omega Centauri","clu",3.9],
["NGC 6543",17.976,66.63,"Cat's Eye Nebula","neb",8.1],["NGC 6888",20.202,38.35,"Crescent Nebula","neb",7.4],["NGC 6960",20.761,30.72,"Western Veil","neb",7.0],
["NGC 6992",20.940,31.72,"Eastern Veil","neb",7.0],["NGC 7000",20.979,44.33,"North America Nebula","neb",4.0],["IC 5070",20.848,44.35,"Pelican Nebula","neb",8.0],
["IC 1396",21.650,57.50,"Elephant's Trunk","neb",3.5],["NGC 7023",21.027,68.17,"Iris Nebula","neb",6.8],["NGC 7293",22.494,-20.84,"Helix Nebula","neb",7.6],
["NGC 7331",22.618,34.42,"Galaxy","gal",9.5],["NGC 7635",23.345,61.20,"Bubble Nebula","neb",10.0],["NGC 7789",23.957,56.72,"Caroline's Rose","clu",6.7],
["NGC 2070",5.644,-69.10,"Tarantula Nebula","neb",8.0],["NGC 3372",10.752,-59.87,"Carina Nebula","neb",1.0]];
const TYPE={neb:'Nebula',gal:'Galaxy',clu:'Cluster'};
function altWord(a){return a>=30?'high':a>=15?'fair':a>=0?'low':'below horizon';}
function renderPlanner(){const loc=getLoc(),q=$('p_q').value.trim().toLowerCase(),ty=$('p_type').value,so=$('p_sort').value;
  $('locBadge').textContent=loc?('altitudes for '+loc.lat.toFixed(1)+'\u00b0, '+loc.lon.toFixed(1)+'\u00b0'+(loc.src==='scope'?' (from scope)':'')):'set a location in Settings for altitudes';
  if(loc){const s=sunAlt(loc);$('skyNow').textContent=s<-12?'\u2022 dark sky now':s<-0.8?'\u2022 twilight now':'\u2022 daylight now (Sun '+s.toFixed(0)+'\u00b0)';}
  let rows=CAT.map(c=>({n:c[0],ra:c[1],dec:c[2],cn:c[3],ty:c[4],mag:c[5],alt:loc?altOf(c[1],c[2],loc):null}));
  if(q)rows=rows.filter(r=>(r.n+' '+r.n.replace(' ','')+' '+r.cn+' '+TYPE[r.ty]).toLowerCase().includes(q));
  if(ty)rows=rows.filter(r=>r.ty===ty);
  rows.sort(so==='name'?(a,b)=>a.n.localeCompare(b.n,undefined,{numeric:true}):so==='mag'||!loc?(a,b)=>a.mag-b.mag:(a,b)=>b.alt-a.alt);
  const cur=$('t_name').value;
  $('plist').innerHTML=rows.map(r=>{const a=r.alt,tr=loc?transit(r.ra,loc):null,mx=loc?90-Math.abs(loc.lat-r.dec):null;
    return '<button class="pit'+(a!=null&&a<15?' low':'')+(r.n===cur?' sel':'')+'" onclick="pick(\''+r.n+'\')"><span class="n">'+r.n+'<small>'+esc(r.cn)+'</small></span>'+
    '<span class="a">'+(a!=null?(a>=0?a.toFixed(0)+'\u00b0':'\u2014'):'')+'</span>'+
    '<span class="m"><span>'+TYPE[r.ty]+' \u00b7 mag '+r.mag+(a!=null?' \u00b7 '+altWord(a):'')+'</span>'+
    (a!=null&&a>=0?'<span class="altbar"><i style="width:'+Math.min(100,a/90*100)+'%"></i></span>':'<span style="flex:1"></span>')+
    (tr&&mx>0?'<span>peak '+mx.toFixed(0)+'\u00b0 at '+hm(tr)+'</span>':'')+'</span></button>';}).join('')||'<div class="hint">No match.</div>';
  renderSolar();renderFavs();drawSky();}
function pick(n){const c=CAT.find(x=>x[0]===n);if(!c)return;$('t_name').value=c[0];$('t_ra').value=c[1];$('t_dec').value=c[2];$('t_mode').value='star';
  $('t_lp').checked=c[4]==='neb';tgtInfo();renderPlanner();}
function tgtInfo(){const ra=parseCoord($('t_ra').value),dec=parseCoord($('t_dec').value),loc=getLoc(),el=$('t_info'),mode=$('t_mode').value;
  $('frmRow').style.display=mode==='star'?'':'none';$('bScan').style.display=mode==='star'?'none':'';
  if(isNaN(ra)||isNaN(dec)){el.textContent='Pick a target from the lists or the sky map, or type coordinates.';return null;}
  if(ra<0||ra>=24||Math.abs(dec)>90){el.textContent='RA must be 0\u201324 h and Dec \u221290\u2026+90\u00b0.';return null;}
  let a=null;if(loc){a=altOf(ra,dec,loc);el.textContent='Altitude now: '+a.toFixed(0)+'\u00b0 ('+altWord(a)+') \u00b7 peaks at '+hm(transit(ra,loc));}
  else el.textContent='RA '+ra.toFixed(4)+' h, Dec '+dec.toFixed(3)+'\u00b0';
  return {ra,dec,alt:a,mode,name:$('t_name').value.trim()||'Target',lp:$('t_lp').checked};}
async function gotoManual(){const t=tgtInfo();if(!t){toast('Enter a valid RA and Dec','bad');return;}
  let msg='The mount will slew to RA '+t.ra.toFixed(3)+' h, Dec '+t.dec.toFixed(2)+'\u00b0'+(t.mode==='star'?' and start imaging.':' in '+t.mode+' mode.');
  if(planRunning())msg+=' This INTERRUPTS the plan running on the scope.';
  else if(isStacking())msg+=' This ENDS the session running on '+(S.target.name||'the current target')+'.';
  if(t.alt!=null&&t.alt<10)msg+=' Warning: this target is only '+t.alt.toFixed(0)+'\u00b0 above the horizon right now.';
  if(t.mode==='sun')msg+=' MAKE SURE THE SOLAR FILTER IS FITTED.';
  if(!(await ask('GoTo '+t.name+'?',msg,'Slew')))return;
  let ok;if(t.mode==='star'){const sc=parseFloat($('t_scale').value)||1,an=parseFloat($('t_angle').value)||0,p={target_name:t.name,ra:t.ra,dec:t.dec,lp:t.lp};
    if(sc>1||an)p.mosaic={scale:Math.min(2,Math.max(1,sc)),angle:an};ok=await act('goto',p);}
  else ok=await act('start_view',{mode:t.mode,target_name:t.name,ra:t.ra,dec:t.dec,lp:false});
  if(ok){let r=lsGet('recent',[]).filter(x=>x.n!==t.name);r.unshift({n:t.name,ra:t.ra,dec:t.dec,mode:t.mode});lsSet('recent',r.slice(0,8));renderFavs();sel('live');}}
async function slewOnly(){const t=tgtInfo();if(!t){toast('Enter a valid RA and Dec','bad');return;}
  if(t.mode==='sun'){toast('Use GoTo for the Sun so the solar-mode safety applies','bad');return;}
  if(await ask('Slew to '+t.name+'?','Moves the mount only \u2014 no plate-solve, no imaging.'+(isStacking()?' Stacking is running and will be disturbed.':''),'Slew'))act('slew',{ra:t.ra,dec:t.dec});}
async function syncMount(){const t=tgtInfo();if(!t){toast('Put the true coordinates in the GoTo box on the Targets tab first','bad');return;}
  if(await ask('Sync the mount?','Tells the mount it is currently pointing at RA '+t.ra.toFixed(3)+' h, Dec '+t.dec.toFixed(2)+'\u00b0. Only do this if the target really is centred.','Sync'))act('sync',{ra:t.ra,dec:t.dec});}
// favourites & recent
function favAdd(){const t=tgtInfo();if(!t){toast('Enter a target first','bad');return;}let f=lsGet('favs',[]).filter(x=>x.n!==t.name);
  f.unshift({n:t.name,ra:t.ra,dec:t.dec,mode:t.mode});lsSet('favs',f.slice(0,30));renderFavs();toast('Added to favourites','ok');}
function favDel(n){lsSet('favs',lsGet('favs',[]).filter(x=>x.n!==n));renderFavs();}
function favPick(kind,i){const x=lsGet(kind,[])[i];if(!x)return;$('t_name').value=x.n;$('t_ra').value=x.ra;$('t_dec').value=x.dec;$('t_mode').value=x.mode||'star';tgtInfo();
  if(x.mode&&x.mode!=='star'&&BODIES.some(b=>b[0]===x.n))pickBody(x.n);}
function renderFavs(){const f=lsGet('favs',[]),r=lsGet('recent',[]);
  $('favs').innerHTML=(f.map((x,i)=>'<span class="chip" onclick="favPick(\'favs\','+i+')">\u2605 '+esc(x.n)+'<small onclick="event.stopPropagation();favDel(\''+esc(x.n).replace(/&#39;/g,"\\'")+'\')" title="remove">\u2715</small></span>').join('')+
    r.map((x,i)=>'<span class="chip" onclick="favPick(\'recent\','+i+')">'+esc(x.n)+'<small>recent</small></span>').join(''))||'<span class="hint" style="margin:0">Targets you star or GoTo show up here.</span>';}
// sky map
function altAz(ra,dec,loc,t){const ha=(lstH(t||Date.now(),loc.lon)-ra)*15*R,d=dec*R,p=loc.lat*R,
  alt=Math.asin(Math.sin(d)*Math.sin(p)+Math.cos(d)*Math.cos(p)*Math.cos(ha));
  let az=Math.atan2(Math.sin(ha),Math.cos(ha)*Math.sin(p)-Math.tan(d)*Math.cos(p))/R+180;return {alt:alt/R,az:((az%360)+360)%360};}
let SKY=[];
function drawSky(){const cv=$('sky'),W=cv.clientWidth;if(!W){if(curView==='target')setTimeout(drawSky,400);return;}const dpr=window.devicePixelRatio||1;cv.width=W*dpr;cv.height=W*dpr;cv.style.height=W+'px';
  const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);const c=W/2,Rr=W/2-14,loc=getLoc();x.clearRect(0,0,W,W);
  x.fillStyle='rgba(8,12,24,.9)';x.beginPath();x.arc(c,c,Rr,0,6.29);x.fill();x.strokeStyle='rgba(90,120,170,.22)';x.lineWidth=1;
  [1,2/3,1/3].forEach(f=>{x.beginPath();x.arc(c,c,Rr*f,0,6.29);x.stroke();});
  x.fillStyle='#8ba0c4';x.font='11px "Segoe UI",system-ui,sans-serif';x.textAlign='center';x.textBaseline='middle';
  [['N',0,-1],['S',0,1],['E',-1,0],['W',1,0]].forEach(([t,dx,dy])=>x.fillText(t,c+dx*(Rr+8),c+dy*(Rr+8)));
  SKY=[];if(!loc){x.fillText('Set your location in Settings',c,c);return;}
  const P=(ra,dec)=>{const h=altAz(ra,dec,loc);if(h.alt<0)return null;const r=(90-h.alt)/90*Rr;return {x:c-r*Math.sin(h.az*R),y:c-r*Math.cos(h.az*R),alt:h.alt};};
  const cur=$('t_name').value;
  CAT.forEach(o=>{const p=P(o[1],o[2]);if(!p)return;const s=o[0]===cur;x.fillStyle=s?'#e8eefb':p.alt>=30?'rgba(110,168,255,.9)':'rgba(110,168,255,.4)';
    x.beginPath();x.arc(p.x,p.y,s?4:2.2,0,6.29);x.fill();if(s){x.fillStyle='#e8eefb';x.fillText(o[0],p.x,p.y-11);}SKY.push({x:p.x,y:p.y,f:()=>pick(o[0])});});
  BODIES.forEach(([n,m,sym])=>{const b=bodyPos(n),p=P(b.ra,b.dec);if(!p)return;x.fillStyle=n==='Sun'?'#ffd166':'#e8eefb';x.font='15px "Segoe UI Symbol",sans-serif';
    x.fillText(sym,p.x,p.y);x.font='10px "Segoe UI",system-ui,sans-serif';x.fillStyle='#8ba0c4';x.fillText(n,p.x,p.y+12);x.font='11px "Segoe UI",system-ui,sans-serif';
    SKY.push({x:p.x,y:p.y,f:()=>pickBody(n)});});
  if(S&&S.connected&&S.target&&S.target.ra!=null&&!(S.mount&&S.mount.close)){const p=P(S.target.ra,S.target.dec);if(p){x.strokeStyle='#39d98a';x.lineWidth=2;
    x.beginPath();x.arc(p.x,p.y,7,0,6.29);x.moveTo(p.x-11,p.y);x.lineTo(p.x+11,p.y);x.moveTo(p.x,p.y-11);x.lineTo(p.x,p.y+11);x.stroke();}}}
$('sky').addEventListener('click',e=>{const r=$('sky').getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=22*22;
  SKY.forEach(o=>{const d=(o.x-mx)**2+(o.y-my)**2;if(d<bd){bd=d;best=o;}});if(best)best.f();});

// ---------- plan mode (runs on the scope: set_view_plan) ----------
let PLAN=lsGet('plan',{name:'Tonight',list:[]});$('pl_name').value=PLAN.name||'Tonight';
function planSave(){lsSet('plan',PLAN);}
const p2=n=>String(n).padStart(2,'0');
function hm2min(s){const m=/^(\d{1,2}):(\d{2})$/.exec(s||'');return m?(+m[1])*60+(+m[2]):NaN;}
function min2hm(m){m=((m%1440)+1440)%1440;return p2(Math.floor(m/60))+':'+p2(m%60);}
function planAdd(){const t=tgtInfo();if(!t){toast('Pick or enter a target first','bad');return;}
  if(t.mode!=='star'){toast('Plans are for deep-sky targets','bad');return;}
  let start;const L=PLAN.list;if(L.length){const last=L[L.length-1];start=min2hm(hm2min(last.start)+(+last.dur||60));}
  else{const d=new Date();start=min2hm(Math.ceil((d.getHours()*60+d.getMinutes()+5)/10)*10);}
  L.push({name:t.name,ra:+t.ra.toFixed(5),dec:+t.dec.toFixed(4),lp:t.lp,start,dur:60});planSave();renderPlan();toast('Added '+t.name+' to the plan ('+start+')','ok');}
function planSet(i,k,v){PLAN.list[i][k]=k==='dur'?Math.max(1,parseInt(v,10)||60):k==='lp'?!!v:k==='mos'?Math.max(1,Math.min(2,parseFloat(v)||1)):v;planSave();if(k!=='name')renderPlan();}
// copy the plan that is on the scope into the builder, so last night's plan can be re-run or tweaked
function planFromScope(){const vp=S&&S.plan&&S.plan.plan;if(!vp||!(vp.list||[]).length){toast('There is no plan on the scope to copy','bad');return;}
  PLAN={name:vp.plan_name||'Tonight',list:vp.list.map(it=>({name:it.target_name||it.alias_name||'Target',ra:+(+it.target_ra_dec[0]).toFixed(5),dec:+(+it.target_ra_dec[1]).toFixed(4),
    lp:!!it.lp_filter,start:min2hm(it.start_min||0),dur:it.duration_min||60,mos:it.mosaic&&it.mosaic.scale>1?+it.mosaic.scale:1}))};
  $('pl_name').value=PLAN.name;planSave();renderPlan();toast('Copied '+PLAN.list.length+' targets from the scope — check the start times, then send','ok');}
function planDel(i){PLAN.list.splice(i,1);planSave();renderPlan();}
function planMove(i,d){const L=PLAN.list,j=i+d;if(j<0||j>=L.length)return;[L[i],L[j]]=[L[j],L[i]];planSave();renderPlan();}
function planClearLocal(){PLAN.list=[];planSave();renderPlan();}
function planTimes(){const now=new Date(),nowM=now.getHours()*60+now.getMinutes();let prev=-1;
  return PLAN.list.map((it,i)=>{let m=hm2min(it.start);if(isNaN(m))return null;if(i===0){if(m<nowM-60)m+=1440;}else{while(m<prev)m+=1440;}prev=m;return m;});}
function renderPlan(){const L=PLAN.list,tm=planTimes(),loc=getLoc();$('pl_empty').style.display=L.length?'none':'';
  $('pl_rows').innerHTML=L.map((it,i)=>{let note='';if(tm[i]!=null){const end=tm[i]+(+it.dur||0);note='ends '+min2hm(end)+(tm[i]>=1440?' (after midnight)':'');
      if(i+1<L.length&&tm[i+1]!=null&&end>tm[i+1])note+=' \u00b7 overlaps the next target (it will be cut short)';
      if(loc){const d=new Date();d.setHours(0,0,0,0);const a=altOf(it.ra,it.dec,loc,d.getTime()+(tm[i]+(+it.dur||0)/2)*60000);note+=' \u00b7 altitude ~'+a.toFixed(0)+'\u00b0 mid-run'+(a<15?' (LOW)':'');
        const hh=altAz(it.ra,it.dec,loc,d.getTime()+(tm[i]+(+it.dur||0)/2)*60000);if(skyBlocked(hh.alt,hh.az))note+=' \u00b7 <span style="color:var(--warn)">behind your skyline mid-run</span>';}}
    else note='enter a start time as HH:MM';
    return '<div class="prow"><div class="ph"><b>'+(i+1)+'. </b><input value="'+esc(it.name)+'" onchange="planSet('+i+',\'name\',this.value)" aria-label="Target name">'+
      '<button class="btn sm ghost" onclick="planMove('+i+',-1)" title="Move up">\u2191</button><button class="btn sm ghost" onclick="planMove('+i+',1)" title="Move down">\u2193</button>'+
      '<button class="btn sm bad" onclick="planDel('+i+')" title="Remove">\u2715</button></div>'+
      '<div class="pf"><label>Start<input type="time" value="'+esc(it.start)+'" onchange="planSet('+i+',\'start\',this.value)"></label>'+
      '<label>Minutes<input type="number" min="1" max="720" value="'+(+it.dur||60)+'" onchange="planSet('+i+',\'dur\',this.value)"></label>'+
      '<label title="1 = normal frame. Up to 2 = the scope shifts around to cover a wider field (mosaic).">Mosaic ×<input type="number" min="1" max="2" step="0.1" value="'+(+it.mos||1)+'" onchange="planSet('+i+',\'mos\',this.value)"></label>'+
      '<label class="ck"><input type="checkbox" '+(it.lp?'checked':'')+' onchange="planSet('+i+',\'lp\',this.checked)"> LP filter</label></div>'+
      '<div class="hint" style="margin-top:4px">RA '+(+it.ra).toFixed(3)+' h, Dec '+(+it.dec).toFixed(2)+'\u00b0 \u00b7 '+note+'</div></div>';}).join('');}
async function planSend(){const L=PLAN.list,tm=planTimes();if(!L.length){toast('Add at least one target','bad');return;}
  if(tm.some(x=>x==null)){toast('Every target needs a start time (HH:MM)','bad');return;}
  if(!S||!S.connected){toast('Scope is offline - the plan was not sent','bad');return;}
  const list=L.map((it,i)=>{const o={name:it.name,alias:it.name,ra:it.ra,dec:it.dec,lp:!!it.lp,start_min:tm[i],duration_min:+it.dur||60};if(+it.mos>1)o.mosaic={scale:+it.mos,angle:0};return o;});
  let msg=L.length+' target'+(L.length>1?'s':'')+', '+min2hm(tm[0])+' \u2192 '+min2hm(tm[L.length-1]+(+L[L.length-1].dur||60))+'. The scope will slew and image on its own.';
  if(isStacking()||planRunning())msg+=' This REPLACES what the scope is doing now.';
  if(!(await ask('Send "'+(PLAN.name||'plan')+'" to the scope?',msg,'Send & start')))return;
  await act('sync_time',{tz:tzName()},true);
  if(await act('plan_start',{name:PLAN.name||'Studio plan',list}))toast('Plan is on the scope','ok');}
const PST={working:'running',complete:'done',cancel:'stopped',idle:'waiting',fail:'failed'};
function renderRun(){const vp=S&&S.connected?S.plan:null;if(!vp||!vp.plan){$('pl_state').textContent=S&&S.connected?'no plan':'scope offline';
    $('pl_run').innerHTML='<div class="hint">'+(S&&S.connected?'No plan is loaded on the scope.':'Connect to the scope to see its plan.')+'</div>';return;}
  $('pl_state').textContent=PST[vp.state]||vp.state||'loaded';
  $('pl_run').innerHTML='<div class="row"><span class="k">Name</span><span>'+esc(vp.plan.plan_name||'')+'</span></div>'+(vp.plan.list||[]).map(it=>
    '<div class="row"><span><b>'+esc(it.target_name||'')+'</b> <span class="k">'+min2hm(it.start_min||0)+' \u00b7 '+(it.duration_min||0)+' min</span></span>'+
    '<span>'+(it.skip?'skipped':(PST[it.state]||it.state||'waiting'))+(it.state==='working'&&it.lapse_ms?' \u00b7 '+Math.round(it.lapse_ms/60000)+' min in':'')+'</span></div>'+
    ((it.mosaic||it.lp_filter||it.stack_total_sec||it.error)?'<div class="hint" style="margin:-2px 0 6px">'+[it.mosaic&&it.mosaic.scale>1?'mosaic \u00d7'+it.mosaic.scale:'',it.lp_filter?'LP filter':'',
      it.stack_total_sec?fmtHMS(it.stack_total_sec)+' stacked':'',it.error?'<span style="color:var(--bad)">stopped: '+esc(it.error)+'</span>':''].filter(Boolean).join(' \u00b7 ')+'</div>':'')).join('');}

// ---------- 3D scope view ----------
const V3={yaw:0.6,pitch:0.26,dist:10.5,p:null,d:[1,0,0],drag:null};
const V3R=4.4,V3HUB=1.75,V3BALL=[0,0,1.9],V3STEM=0.42;
const v3add=(a,b)=>[a[0]+b[0],a[1]+b[1],a[2]+b[2]],v3sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]],v3mul=(a,k)=>[a[0]*k,a[1]*k,a[2]*k];
const v3dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2],v3cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const v3len=a=>Math.sqrt(v3dot(a,a)),v3norm=a=>{const l=v3len(a)||1;return [a[0]/l,a[1]/l,a[2]/l];};
const v3lerp=(a,b,t)=>v3add(a,v3mul(v3sub(b,a),t));
// world: x = east, y = north, z = up
function v3dir(alt,az){const a=alt*Math.PI/180,z=az*Math.PI/180;return [Math.cos(a)*Math.sin(z),Math.cos(a)*Math.cos(z),Math.sin(a)];}
function v3box(c,ax,ay,az,hx,hy,hz,col,polys,frontCol){
  const P=(i,j,k)=>v3add(c,v3add(v3mul(ax,i*hx),v3add(v3mul(ay,j*hy),v3mul(az,k*hz))));
  const F=[[ax,[[1,-1,-1],[1,1,-1],[1,1,1],[1,-1,1]],frontCol||col],[v3mul(ax,-1),[[-1,-1,-1],[-1,-1,1],[-1,1,1],[-1,1,-1]],col],
           [ay,[[-1,1,-1],[-1,1,1],[1,1,1],[1,1,-1]],col],[v3mul(ay,-1),[[-1,-1,-1],[1,-1,-1],[1,-1,1],[-1,-1,1]],col],
           [az,[[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]],col],[v3mul(az,-1),[[-1,-1,-1],[-1,1,-1],[1,1,-1],[1,-1,-1]],col]];
  F.forEach(([n,q,cl])=>polys.push({n,v:q.map(s=>P(s[0],s[1],s[2])),col:cl}));}
function v3prism(c0,axis,r,h,col,polys){const u=v3norm(Math.abs(axis[2])<0.9?v3cross(axis,[0,0,1]):v3cross(axis,[1,0,0])),w=v3cross(axis,u),N=20,top=[],bot=[];
  for(let i=0;i<N;i++){const t=i/N*2*Math.PI,o=v3add(v3mul(u,Math.cos(t)*r),v3mul(w,Math.sin(t)*r));bot.push(v3add(c0,o));top.push(v3add(c0,v3add(o,v3mul(axis,h))));}
  for(let i=0;i<N;i++){const j=(i+1)%N,t=(i+0.5)/N*2*Math.PI;polys.push({n:v3add(v3mul(u,Math.cos(t)),v3mul(w,Math.sin(t))),v:[bot[i],bot[j],top[j],top[i]],col});}
  polys.push({n:axis,v:top,col});polys.push({n:v3mul(axis,-1),v:bot.slice().reverse(),col});}
function compass16(az){return ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round(((az%360)+360)%360/22.5)%16];}
// small mesh builder for the WebGL parts (tripod, head)
function v3mesh(){const P=[],N=[],C=[];
  const tri=(a,b,c,na,nb,nc,col)=>{[[a,na],[b,nb],[c,nc]].forEach(([p,n])=>{P.push(p[0],p[1],p[2]);N.push(n[0],n[1],n[2]);C.push(col[0]/255,col[1]/255,col[2]/255);});};
  const M={P,N,C,
    cyl(a,b,ra,rb,col){const ax=v3norm(v3sub(b,a)),u=v3norm(Math.abs(ax[2])<0.9?v3cross(ax,[0,0,1]):v3cross(ax,[1,0,0])),w=v3cross(ax,u),n=20,m=v3mul(ax,-1);
      for(let i=0;i<n;i++){const t0=i/n*6.28319,t1=(i+1)/n*6.28319,d0=v3add(v3mul(u,Math.cos(t0)),v3mul(w,Math.sin(t0))),d1=v3add(v3mul(u,Math.cos(t1)),v3mul(w,Math.sin(t1)));
        const a0=v3add(a,v3mul(d0,ra)),a1=v3add(a,v3mul(d1,ra)),b0=v3add(b,v3mul(d0,rb)),b1=v3add(b,v3mul(d1,rb));
        tri(a0,a1,b1,d0,d1,d1,col);tri(a0,b1,b0,d0,d1,d0,col);tri(b,b0,b1,ax,ax,ax,col);tri(a,a1,a0,m,m,m,col);}return M;},
    sph(c,r,col){const nu=10,nv=18,pt=(i,j)=>{const th=i/nu*Math.PI,ph=j/nv*6.28319;return [Math.sin(th)*Math.cos(ph),Math.sin(th)*Math.sin(ph),Math.cos(th)];},q=n=>v3add(c,v3mul(n,r));
      for(let i=0;i<nu;i++)for(let j=0;j<nv;j++){const n00=pt(i,j),n10=pt(i+1,j),n11=pt(i+1,j+1),n01=pt(i,j+1);
        tri(q(n00),q(n10),q(n11),n00,n10,n11,col);tri(q(n00),q(n11),q(n01),n00,n11,n01,col);}return M;}};
  return M;}
// real scope model (WebGL), loaded from /api/model; the block model is the fallback
const V3M={ready:false,pivot:1.05,credit:''};
function v3b64(s,T){const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return new T(u.buffer);}
function v3load(){fetch('/api/model').then(r=>r.ok?r.json():Promise.reject(new Error('no model'))).then(m=>{
  const gc=document.createElement('canvas'),gl=gc.getContext('webgl',{alpha:true,antialias:true,preserveDrawingBuffer:true});if(!gl)throw new Error('no webgl');
  const sh=(t,s)=>{const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(o));return o;};
  const VS='attribute vec3 aP,aN,aC;uniform vec3 uO,uX,uY,uZ,uCam,uR,uU,uF;uniform vec3 uPr;varying vec3 vC,vN,vW;'+
    'void main(){vec3 w=uO+aP.x*uX+aP.y*uY+aP.z*uZ;vN=aN.x*uX+aN.y*uY+aN.z*uZ;vC=aC;vW=uCam-w;vec3 q=w-uCam;float z=dot(q,uF);'+
    'gl_Position=vec4(uPr.x*dot(q,uR),uPr.y*dot(q,uU)+uPr.z*z,z*1.0202-1.0101,z);}';
  const FS='precision mediump float;varying vec3 vC,vN,vW;'+
    'void main(){vec3 n=normalize(vN),v=normalize(vW);if(dot(n,v)<0.0)n=-n;vec3 L=normalize(vec3(-0.45,-0.55,0.75));'+
    'float d=max(dot(n,L),0.0),d2=max(dot(n,normalize(vec3(0.7,0.45,0.15))),0.0),sp=pow(max(dot(n,normalize(L+v)),0.0),28.0);'+
    'gl_FragColor=vec4(vC*(0.36+0.60*d+0.16*d2)+vec3(0.16)*sp,1.0);}';
  const pg=gl.createProgram();gl.attachShader(pg,sh(gl.VERTEX_SHADER,VS));gl.attachShader(pg,sh(gl.FRAGMENT_SHADER,FS));gl.linkProgram(pg);
  if(!gl.getProgramParameter(pg,gl.LINK_STATUS))throw new Error('shader link: '+gl.getProgramInfoLog(pg));
  const mk=a=>{const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,a,gl.STATIC_DRAW);return b;};
  const up=M=>({n:M.P.length/3,pos:mk(new Float32Array(M.P)),nor:mk(new Float32Array(M.N)),col:mk(new Float32Array(M.C))});
  const parts={};
  Object.keys(m.parts).forEach(k=>{const P=m.parts[k],v=v3b64(P.v,Int16Array),ix=v3b64(P.i,Uint16Array),c=v3b64(P.c,Uint8Array),T=P.t;
    const pos=new Float32Array(T*9),nor=new Float32Array(T*9),col=new Float32Array(T*9);
    for(let t=0;t<T;t++){const q=[];for(let j=0;j<3;j++){const i=ix[t*3+j]*3;q.push([v[i]/10000,v[i+1]/10000,v[i+2]/10000]);}
      const n=v3norm(v3cross(v3sub(q[1],q[0]),v3sub(q[2],q[0]))),pc=m.palette[c[t]];
      for(let j=0;j<3;j++){const o=t*9+j*3;pos[o]=q[j][0];pos[o+1]=q[j][1];pos[o+2]=q[j][2];nor[o]=n[0];nor[o+1]=n[1];nor[o+2]=n[2];col[o]=pc[0]/255;col[o+1]=pc[1]/255;col[o+2]=pc[2]/255;}}
    parts[k]={n:T*3,pos:mk(pos),nor:mk(nor),col:mk(col)};});
  // tripod, in world coordinates
  const tp=v3mesh(),leg=[46,50,60],metal=[92,98,112];
  [30,150,270].forEach(a=>{const e=v3dir(0,a),top=[e[0]*0.17,e[1]*0.17,V3HUB-0.13],foot=[e[0]*1.35,e[1]*1.35,0.05],mid=v3lerp(top,foot,0.52);
    tp.cyl(top,mid,0.085,0.075,leg).cyl(mid,foot,0.058,0.046,leg).cyl(v3lerp(top,foot,0.49),v3lerp(top,foot,0.55),0.092,0.092,metal).sph(foot,0.07,[26,28,34]).sph(top,0.1,metal);});
  tp.cyl([0,0,V3HUB-0.32],[0,0,V3HUB],0.23,0.23,metal).cyl([0,0,V3HUB],[0,0,V3BALL[2]-0.06],0.13,0.16,[60,64,76]);
  parts.tripod=up(tp);
  // tilt head, in scope-local coordinates (x runs up the axis, 0 = underside of the scope)
  const hd=v3mesh();hd.sph([-V3STEM,0,0],0.17,[128,134,148]).cyl([-V3STEM,0,0],[-0.07,0,0],0.075,0.075,metal).cyl([-0.07,0,0],[0,0,0],0.33,0.33,[58,62,74]);
  parts.head=up(hd);
  V3M.gc=gc;V3M.gl=gl;V3M.pg=pg;V3M.parts=parts;V3M.pivot=m.pivot[0];V3M.credit=m.credit||'';V3M.ready=true;
}).catch(e=>{V3M.ready=false;console.warn('3D model unavailable, using block model:',e&&e.message);});}
function v3render(g,W,H,dpr,cam,r,u,f,Fo,O,A,Fw,D,piv,p,T2){
  const gl=V3M.gl,gc=V3M.gc,pg=V3M.pg,w=Math.round(W*dpr),h=Math.round(H*dpr);
  if(gc.width!==w||gc.height!==h){gc.width=w;gc.height=h;}
  gl.viewport(0,0,w,h);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);gl.useProgram(pg);
  const U=(n,v)=>gl.uniform3f(gl.getUniformLocation(pg,n),v[0],v[1],v[2]);
  U('uCam',cam);U('uR',r);U('uU',u);U('uF',f);U('uPr',[2*Fo/W,2*Fo/H,1-2*0.56]);
  const draw=(part,o,x,y,z)=>{U('uO',o);U('uX',x);U('uY',y);U('uZ',z);
    [['aP',part.pos],['aN',part.nor],['aC',part.col]].forEach(([nm,b])=>{const l=gl.getAttribLocation(pg,nm);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.enableVertexAttribArray(l);gl.vertexAttribPointer(l,3,gl.FLOAT,false,0,0);});
    gl.drawArrays(gl.TRIANGLES,0,part.n);};
  draw(V3M.parts.tripod,[0,0,0],[1,0,0],[0,1,0],[0,0,1]);draw(V3M.parts.head,O,A,Fw,D);
  draw(V3M.parts.body,O,A,Fw,D);draw(V3M.parts.tube,piv,T2,p,D);
  g.drawImage(gc,0,0,W,H);}
function draw3d(){
  const cv=$('v3d');if(!cv)return;const W=cv.clientWidth;if(!W)return;const H=Math.round(Math.min(W*0.7,520)),dpr=window.devicePixelRatio||1;
  if(cv.width!==Math.round(W*dpr)||cv.height!==Math.round(H*dpr)){cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);cv.style.height=H+'px';}
  const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);
  const d=S||{},mt=d.mount||{},az=d.altaz,gl=getLoc(),lat=(d.location&&d.location.lat!=null)?d.location.lat:(gl?gl.lat:40);
  const eq=!!mt.equ_mode,closed=mt.close===true,have=!!(az&&az.alt!=null)&&!closed,useM=V3M.ready,R=V3R;
  const pole=v3dir(Math.abs(lat),lat>=0?0:180),A=eq?pole:[0,0,1];
  // pointing vector, eased toward the latest reading
  const want=have?v3dir(az.alt,az.az):v3mul(A,-1);
  V3.p=V3.p?v3norm(v3add(V3.p,v3mul(v3sub(want,V3.p),0.25))):want;const p=V3.p;
  const cx=v3cross(A,p);if(v3len(cx)>0.02){V3.d=v3norm(cx);}
  else{const perp=v3sub(V3.d,v3mul(A,v3dot(V3.d,A)));V3.d=v3len(perp)>0.05?v3norm(perp):v3norm(v3cross(A,[0,1,0.01]));}
  // scope frame: A = up its axis, Fw = forward, D = the tilt (altitude / Dec) axis
  const D=V3.d,Fw=v3cross(D,A),T2=v3cross(p,D),O=v3add(V3BALL,v3mul(A,V3STEM));
  const piv=v3add(O,v3mul(A,useM?V3M.pivot:0.96));
  const tip=useM?v3add(piv,v3add(v3mul(p,0.62),v3mul(D,0.24))):v3add(piv,v3mul(p,0.5));
  const tb=v3dot(tip,p),end=v3add(tip,v3mul(p,-tb+Math.sqrt(Math.max(0,tb*tb-v3dot(tip,tip)+R*R))));
  const azM=Math.atan2(end[0],end[1])*180/Math.PI,altM=Math.asin(Math.max(-1,Math.min(1,end[2]/R)))*180/Math.PI;
  // camera
  const C=[0,0,1.75],cp=Math.cos(V3.pitch),cam=v3add(C,v3mul([cp*Math.sin(V3.yaw),-cp*Math.cos(V3.yaw),Math.sin(V3.pitch)],V3.dist));
  const f=v3norm(v3sub(C,cam)),r=v3norm(v3cross(f,[0,0,1])),u=v3cross(r,f),Fo=Math.min(W*0.92,H*1.5);
  const pr=P=>{const q=v3sub(P,cam),z=v3dot(q,f);return [W/2+Fo*v3dot(q,r)/z,H*0.56-Fo*v3dot(q,u)/z,z];};
  const line=(pts,col,w,dash)=>{g.beginPath();pts.forEach((P,i)=>{const s=pr(P);i?g.lineTo(s[0],s[1]):g.moveTo(s[0],s[1]);});g.strokeStyle=col;g.lineWidth=w||1;g.setLineDash(dash||[]);g.stroke();g.setLineDash([]);};
  const ring=(alt,n)=>{const a=[];for(let i=0;i<=n;i++)a.push(v3mul(v3dir(alt,i/n*360),R));return a;};
  const label=(P,t,col,font,dy)=>{const s=pr(P);g.font=font||'600 12px system-ui,sans-serif';g.fillStyle=col;g.textAlign='center';g.fillText(t,s[0],s[1]+(dy||0));};
  // ground
  g.beginPath();ring(0,72).forEach((P,i)=>{const s=pr(P);i?g.lineTo(s[0],s[1]):g.moveTo(s[0],s[1]);});g.fillStyle='rgba(40,58,96,.30)';g.fill();
  line(ring(0,72),'rgba(140,170,220,.55)',1.4);
  for(let a=0;a<360;a+=30){const e=v3dir(0,a);line([v3mul(e,R*0.95),v3mul(e,R)],'rgba(140,170,220,.5)',1);}
  [1,2].forEach(k=>{const a=[];for(let i=0;i<=48;i++)a.push(v3mul(v3dir(0,i*7.5),R*k/3));line(a,'rgba(120,150,200,.13)',1);});
  // sky dome
  [30,60].forEach(al=>line(ring(al,60),'rgba(120,150,200,.20)',1));
  for(let a=0;a<360;a+=45){const m=[];for(let i=0;i<=18;i++)m.push(v3mul(v3dir(i*5,a),R));line(m,'rgba(120,150,200,.16)',1);}
  [['N',0,'#ff8a8a'],['E',90,'#8ba0c4'],['S',180,'#8ba0c4'],['W',270,'#8ba0c4']].forEach(([t,a,c])=>label(v3mul(v3dir(0,a),R*1.1),t,c,'700 14px system-ui,sans-serif',5));
  // measured skyline: a dark band from the ground up to the horizon profile
  if(typeof HZ!=='undefined'&&HZ){const up=[],dn=[];for(let a=0;a<=360;a+=2){const h=Math.max(0,skyAlt(a%360)||0);up.push(pr(v3mul(v3dir(h,a),R)));dn.push(pr(v3mul(v3dir(0,a),R)));}
    g.beginPath();up.forEach((q,i)=>i?g.lineTo(q[0],q[1]):g.moveTo(q[0],q[1]));dn.reverse().forEach(q=>g.lineTo(q[0],q[1]));g.closePath();g.fillStyle='rgba(30,44,36,.55)';g.fill();
    g.beginPath();up.forEach((q,i)=>i?g.lineTo(q[0],q[1]):g.moveTo(q[0],q[1]));g.strokeStyle='rgba(255,209,102,.75)';g.lineWidth=1.3;g.stroke();}
  // celestial pole + polar axis
  {const pe=v3add(V3BALL,v3mul(pole,R*0.86));line([V3BALL,pe],'rgba(255,209,102,.38)',1,[4,5]);
    const s=pr(pe);g.beginPath();g.arc(s[0],s[1],3.2,0,7);g.fillStyle='#ffd166';g.fill();label(pe,lat>=0?'to Polaris':'to S. pole','#ffd166','600 11px system-ui,sans-serif',-9);}
  // direction on the ground + altitude arc
  if(have){const gd=v3dir(0,azM);line([[0,0,0],v3mul(gd,R)],'rgba(110,168,255,.5)',1.5,[6,4]);
    const arc=[],n=Math.max(2,Math.round(Math.abs(altM)/3));for(let i=0;i<=n;i++)arc.push(v3mul(v3dir(altM*i/n,azM),R));line(arc,'rgba(110,168,255,.5)',1.5,[6,4]);}
  // sky objects: Sun, Moon, planets and the other targets of the running plan
  {const lc=(d.location&&d.location.lat!=null&&d.location.lon!=null)?d.location:gl;if(lc){
    const dot=(ra,dec,nm,col,rad)=>{const h=altAz(ra,dec,lc);if(h.alt<1)return;const P=v3mul(v3dir(h.alt,h.az),R),s=pr(P);
      g.beginPath();g.arc(s[0],s[1],rad,0,7);g.fillStyle=col;g.fill();label(P,nm,col,'500 10.5px system-ui,sans-serif',-rad-4);};
    BODIES.forEach(b=>{const q=bodyPos(b[0]);dot(q.ra,q.dec,b[0],b[0]==='Sun'?'#ffd166':b[0]==='Moon'?'#dfe6f5':'#c9a27a',(b[0]==='Sun'||b[0]==='Moon')?4.5:2.6);});
    const vp=d.plan&&d.plan.plan;if(vp&&d.plan.state==='working')(vp.list||[]).forEach(it=>{if(it.state==='working'||!it.target_ra_dec)return;
      dot(it.target_ra_dec[0],it.target_ra_dec[1],it.target_name,it.state==='complete'?'rgba(57,217,138,.8)':'rgba(170,145,255,.95)',2.6);});}}
  if(useM)v3render(g,W,H,dpr,cam,r,u,f,Fo,O,A,Fw,D,piv,p,T2);
  else{ // block model fallback
    [30,150,270].forEach(a=>{const e=v3dir(0,a);line([[0,0,V3HUB],[e[0]*1.35,e[1]*1.35,0]],'rgba(170,185,215,.85)',3.2);});
    line([[0,0,V3HUB-0.3],V3BALL],'rgba(170,185,215,.9)',5);line([V3BALL,O],'rgba(170,185,215,.9)',4);
    const polys=[],E=v3cross(A,D),body=[228,233,246],dark=[58,68,92];
    v3prism(O,A,0.36,0.30,dark,polys);
    v3box(v3add(O,v3add(v3mul(A,0.30+0.50),v3mul(D,0.31))),D,E,A,0.085,0.22,0.52,body,polys);
    v3box(piv,p,D,T2,0.50,0.215,0.215,body,polys,[70,120,210]);
    const L=v3norm([-0.45,-0.55,0.75]);
    polys.forEach(q=>{let c=[0,0,0];q.v.forEach(P=>c=v3add(c,P));q.c=v3mul(c,1/q.v.length);q.z=v3len(v3sub(q.c,cam));});
    polys.filter(q=>v3dot(q.n,v3sub(cam,q.c))>0).sort((a,b)=>b.z-a.z).forEach(q=>{const sh=0.38+0.62*Math.max(0,v3dot(v3norm(q.n),L));
      g.beginPath();q.v.forEach((P,i)=>{const s=pr(P);i?g.lineTo(s[0],s[1]):g.moveTo(s[0],s[1]);});g.closePath();
      g.fillStyle='rgb('+q.col.map(x=>Math.round(x*sh)).join(',')+')';g.fill();g.strokeStyle='rgba(8,12,22,.55)';g.lineWidth=0.7;g.stroke();});}
  // line of sight + target
  if(have){line([tip,end],'rgba(110,168,255,.95)',2);
    const s=pr(end),gr=g.createRadialGradient(s[0],s[1],0,s[0],s[1],13);gr.addColorStop(0,'rgba(150,200,255,1)');gr.addColorStop(1,'rgba(110,168,255,0)');
    g.beginPath();g.arc(s[0],s[1],13,0,7);g.fillStyle=gr;g.fill();g.beginPath();g.arc(s[0],s[1],3.5,0,7);g.fillStyle='#fff';g.fill();
    const active=d.view&&d.view.state==='working',nm=active&&d.target&&d.target.name?d.target.name:'';if(nm)label(end,nm,'#e8eefb','600 12.5px system-ui,sans-serif',-16);}
  // read-out
  let t;
  if(!d.connected&&!az)t='No position data — scope offline.';
  else if(closed)t='Parked — arm folded.';
  else if(!have)t='Waiting for position…';
  else t='Pointing <b>'+compass16(az.az)+'</b> (azimuth '+az.az.toFixed(1)+'°), <b>'+(az.alt>=0?az.alt.toFixed(1)+'° above':(-az.alt).toFixed(1)+'° below')+'</b> the horizon'+(d.tracking?' · tracking':'')+'.';
  const lv=d.level,bits=[eq?'EQ mode: base tilted toward '+(lat>=0?'north':'south')+' so its axis points at the pole (ideal tilt '+(90-Math.abs(lat)).toFixed(1)+'° for latitude '+lat.toFixed(1)+'°)':'Alt-az mode: base level'];
  if(lv&&lv.angle!=null)bits.push('tilt sensor '+lv.angle.toFixed(1)+'°');
  $('v3dTxt').innerHTML=t+'<br><span class="hint" style="margin:0">'+bits.join(' · ')+'</span>'+(useM?'<br><span class="hint" style="margin:0;opacity:.7">Scope model: “Seestar S30 Pro – Telescope” by WistowTbone, Thingiverse, CC BY-SA. Tripod and head are generic.</span>':'');
}
(function(){const cv=$('v3d');if(!cv)return;v3load();
  cv.addEventListener('pointerdown',e=>{V3.drag=[e.clientX,e.clientY,V3.yaw,V3.pitch];cv.setPointerCapture(e.pointerId);});
  cv.addEventListener('pointermove',e=>{if(!V3.drag)return;V3.yaw=V3.drag[2]-(e.clientX-V3.drag[0])*0.008;V3.pitch=Math.max(0.03,Math.min(1.45,V3.drag[3]+(e.clientY-V3.drag[1])*0.006));draw3d();});
  const up=()=>{V3.drag=null;};cv.addEventListener('pointerup',up);cv.addEventListener('pointercancel',up);
  cv.addEventListener('dblclick',()=>{V3.yaw=0.6;V3.pitch=0.26;V3.dist=10.5;draw3d();});
  cv.addEventListener('wheel',e=>{e.preventDefault();V3.dist=Math.max(4,Math.min(24,V3.dist*(e.deltaY>0?1.08:0.93)));draw3d();},{passive:false});
  setInterval(()=>{if(curView==='mount'&&!document.hidden)draw3d();},120);})();

// ---------- wide-angle camera (picture-in-picture in video modes) ----------
let wideOn=false,camSwap=false;
function setWide(want){const w=$('vidW');
  if(want&&!wideOn){wideOn=true;w.onerror=()=>{wideOn=false;w.style.display='none';};w.src='/api/video?cam='+(camSwap?'tele':'wide')+'&t='+Date.now();w.style.display='block';}
  else if(!want&&wideOn){wideOn=false;w.removeAttribute('src');w.style.display='none';}}
function swapCams(){camSwap=!camSwap;const t=Date.now();if(vidOn)$('vid').src='/api/video?cam='+(camSwap?'wide':'tele')+'&t='+t;if(wideOn)$('vidW').src='/api/video?cam='+(camSwap?'tele':'wide')+'&t='+t;
  $('vidW').title=(camSwap?'Telescope':'Wide-angle')+' camera - click to swap';toast(camSwap?'Wide-angle camera in the main view':'Telescope camera in the main view','ok');}

// ---------- skyline: the local horizon, measured with the wide camera ----------
let HZ=null,hzStamp=null,skState='';
async function loadHorizon(){try{const j=await (await fetch('/api/horizon')).json();HZ=(j.horizon&&j.horizon.profile)?j.horizon:null;drawSkyPano();}catch(e){}}
function skyAlt(az){if(!HZ)return null;const p=HZ.profile,a=((az%360)+360)%360,i=Math.floor(a)%360,v0=p[i],v1=p[(i+1)%360];
  if(v0==null)return v1;if(v1==null)return v0;return v0+(v1-v0)*(a-Math.floor(a));}
function skyBlocked(alt,az){const h=skyAlt(az);return h!=null&&alt<h;}
async function skyScan(){if(!S||!S.connected){toast('Scope is offline','bad');return;}
  if(!(await ask('Scan the skyline now?','The scope parks, then turns half a circle each way from its home position while the wide camera photographs the horizon. It needs enough light to tell sky from trees and roofs - twilight or daytime works best. Cable protection: it never makes a full turn, and it unwinds before parking. Make sure the power cable has slack for half a turn in both directions.','Start scan')))return;
  const {data}=await post('/api/skyline',{action:'start',max_alt:+$('sk_max').value});
  if(data&&data.ok)toast('Skyline scan started','ok');else toast((data&&data.error)||'Could not start the scan','bad');}
async function skyArm(){
  if(!(await ask('Scan at the next twilight?','Studio will start the skyline scan by itself the next time the scope has been idle for a minute (no view or plan running) while the Sun is 3.5\u201312\u00b0 below the horizon - after sunset or before sunrise. It stops, turns back and parks before the Sun gets near the horizon, and keeps whatever it photographed. This PC and Studio must stay on. Make sure the power cable has slack for half a turn each way.','Arm it')))return;
  const {data}=await post('/api/skyline',{action:'arm',max_alt:+$('sk_max').value});toast(data&&data.ok?'Armed for the next twilight':'Could not arm the scan',data&&data.ok?'ok':'bad');}
async function skyDisarm(){await post('/api/skyline',{action:'disarm'});toast('Armed scan cancelled','ok');}
async function skyStop(){await post('/api/skyline',{action:'abort'});toast('Stopping the scan - the scope will turn back and park','ok');}
async function skyClear(){if(!(await ask('Forget the saved skyline?','Removes the measured horizon and its panorama picture from this PC.','Forget it')))return;await post('/api/skyline',{action:'clear'});HZ=null;hzStamp=null;drawSkyPano();}
function renderSkyline(d){const sk=d.skyline||{},sc=sk.scan||{},run=sc.state==='running';
  $('sk_go').style.display=run?'none':'';$('sk_stop').style.display=run?'':'none';
  $('sk_arm').style.display=(run||sk.armed)?'none':'';$('sk_disarm').style.display=(!run&&sk.armed)?'':'none';
  let t;if(run)t='<b>Scanning\u2026</b> '+esc(sc.msg||'')+(sc.steps?' \u00b7 '+Math.round(100*sc.step/sc.steps)+'%':'')+'<br><span class="hint" style="margin:0">Base turned '+Math.abs(sc.wind||0).toFixed(0)+'\u00b0 from home (the scan stops itself at 200\u00b0).</span>';
  else if(sc.state==='error')t='<span style="color:var(--bad)">Last scan failed: '+esc(sc.msg||'')+'</span>';
  else if(sc.state==='aborted')t='Last scan was stopped.';
  else t='';
  if(!run)t+=(t?'<br>':'')+(sk.updated?'Skyline measured '+esc(sk.updated)+' \u2014 found for '+(sk.known_deg||0)+' of 360\u00b0.':'No skyline measured yet.');
  if(!run&&sk.updated&&sk.complete===false)t+=' <span style="color:var(--warn)">Partial scan'+(sk.ended==='sun'?' (stopped before sunrise)':'')+'.</span>';
  if(!run&&sk.armed)t+='<br><b>Armed:</b> starts by itself at the next twilight when the scope is idle (up to '+(sk.armed.max_alt||40)+'\u00b0).';
  if(sk.sun_alt!=null)t+='<br><span class="hint" style="margin:0">Sun now '+(sk.sun_alt>=0?sk.sun_alt.toFixed(1)+'\u00b0 above':(-sk.sun_alt).toFixed(1)+'\u00b0 below')+' the horizon \u00b7 a scan may start only when it is more than '+(-sk.sun_start)+'\u00b0 below'+(run&&sc.sun_alt!=null?' and stops itself at 1.5\u00b0 below':'')+'.</span>';
  $('sk_txt').innerHTML=t;
  if(sk.updated!==hzStamp||(skState==='running'&&!run)){hzStamp=sk.updated;loadHorizon();}
  else if(HZ&&curView==='mount'&&$('sk_cv').dataset.ok!=='1')drawSkyPano();skState=sc.state||'';}
function drawSkyPano(){const box=$('sk_box'),im=$('sk_img');if(!HZ){box.style.display='none';return;}
  box.style.display='';const want='/api/skyline.jpg?v='+encodeURIComponent(HZ.updated||'');
  const paint=()=>{const cv=$('sk_cv'),W=im.clientWidth,H=im.clientHeight;if(!W||!H)return;const dpr=window.devicePixelRatio||1;cv.width=W*dpr;cv.height=H*dpr;const g=cv.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);
    const top=HZ.pano.alt_top,bot=HZ.pano.alt_bottom,Y=a=>(top-a)/(top-bot)*H,X=z=>z/360*W;
    g.strokeStyle='rgba(255,255,255,.35)';g.setLineDash([5,5]);g.beginPath();g.moveTo(0,Y(0));g.lineTo(W,Y(0));g.stroke();g.setLineDash([]);
    g.strokeStyle='#ffd166';g.lineWidth=2;g.beginPath();let pen=false;HZ.profile.forEach((a,i)=>{if(a==null){pen=false;return;}const x=X(i+0.5),y=Y(a);pen?g.lineTo(x,y):g.moveTo(x,y);pen=true;});g.stroke();
    g.font='600 11px system-ui,sans-serif';g.fillStyle='#fff';g.textAlign='center';[['N',0],['E',90],['S',180],['W',270]].forEach(([n,z])=>g.fillText(n,Math.max(8,X(z)),14));cv.dataset.ok='1';};
  $('sk_cv').dataset.ok='';im.onload=paint;if(im.getAttribute('src')!==want)im.src=want;else paint();}
window.addEventListener('resize',()=>{if(HZ)drawSkyPano();});
loadHorizon();

// ---------- mount: hold to move ----------
let mvTimer=null,mvBtn=null;
function mvStart(angle,btn){if(mvTimer)mvStop();if(!S||!S.connected){toast('Scope is offline','bad');return;}
  mvBtn=btn;if(btn)btn.classList.add('held');const go=()=>act('mount_move',{speed:+$('spd').value,angle,dur_sec:3},true);go();mvTimer=setInterval(go,2000);}
function mvStop(){if(!mvTimer)return;clearInterval(mvTimer);mvTimer=null;if(mvBtn)mvBtn.classList.remove('held');mvBtn=null;
  act('mount_move',{speed:0,angle:0,dur_sec:0},true);}
document.querySelectorAll('#dpad .btn').forEach(b=>{b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);mvStart(+b.dataset.ang,b);});
  ['pointerup','pointercancel','lostpointercapture'].forEach(ev=>b.addEventListener(ev,mvStop));b.addEventListener('contextmenu',e=>e.preventDefault());});
addEventListener('blur',mvStop);
const KEYANG={ArrowRight:0,ArrowUp:90,ArrowLeft:180,ArrowDown:270};
addEventListener('keydown',e=>{const typing=/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
  if(e.key==='Escape'){closeViewer();$('dlgNo').click();return;}
  if(typing||e.ctrlKey||e.metaKey||e.altKey)return;
  if(curView==='mount'&&e.key in KEYANG){e.preventDefault();if(!e.repeat)mvStart(KEYANG[e.key],document.querySelector('#dpad [data-ang="'+KEYANG[e.key]+'"]'));return;}
  if(/^\d$/.test(e.key)){const i=e.key==='0'?9:+e.key-1;if(NAV[i])sel(NAV[i][0]);}});
addEventListener('keyup',e=>{if(e.key in KEYANG)mvStop();});

// ---------- console ----------
let rpcHist=[];try{rpcHist=JSON.parse(localStorage.getItem('rpcHist')||'[]');}catch(e){}
function drawHist(){$('rpcHist').innerHTML=rpcHist.map(m=>'<option value="'+esc(m)+'">').join('');}drawHist();
async function sendRpc(){let params=null;const pt=$('rpc_p').value.trim(),m=$('rpc_m').value.trim();
  if(!m){toast('Enter a method name','bad');return;}
  if(pt){try{params=JSON.parse(pt);}catch(e){toast('params is not valid JSON','bad');return;}}
  $('rpcOut').textContent='…';
  try{const {data}=await post('/api/rpc',{method:m,params});
    $('rpcOut').textContent=JSON.stringify(data.reply!==undefined?data.reply:data,null,2);
    rpcHist=[m].concat(rpcHist.filter(x=>x!==m)).slice(0,25);localStorage.setItem('rpcHist',JSON.stringify(rpcHist));drawHist();
  }catch(e){$('rpcOut').textContent=String(e);}}
function qm(m){$('rpc_m').value=m;$('rpc_p').value='';}
let logKind='';
$('logf').onclick=e=>{const b=e.target.closest('button');if(!b)return;logKind=b.dataset.k;
  document.querySelectorAll('#logf .btn').forEach(x=>x.classList.toggle('on',x===b));drawLog();};
function drawLog(){const el=$('log');if(!S)return;const atB=el.scrollTop+el.clientHeight>=el.scrollHeight-20;
  el.innerHTML=(S.log||[]).filter(e=>!logKind||e.kind===logKind).map(e=>'<div class="l"><span class="t">'+e.t+'</span><span class="kd '+e.kind+'">'+e.kind+'</span><span>'+esc(e.text)+'</span></div>').join('');
  if(atB)el.scrollTop=el.scrollHeight;}

// ---------- image viewer (wheel zoom + drag) ----------
let vz=1,vx=0,vy=0,drag=null;
function applyV(){$('modalImg').style.transform='translate('+vx+'px,'+vy+'px) scale('+vz+')';}
function openViewer(src,dl,del){vz=1;vx=vy=0;applyV();$('modalImg').src=src;$('viewDl').href=dl||src;$('modal').classList.add('show');
  const b=$('viewDel');b.style.display=del?'':'none';b.onclick=async()=>{if(await ask('Delete from the scope?','This permanently removes the image from the Seestar\'s storage. It cannot be undone.','Delete')){
    if(await act('delete_image',{names:del})){closeViewer();setTimeout(loadAlbums,1500);}}};}
function closeViewer(){$('modal').classList.remove('show');}
function zoomBy(f){vz=Math.max(1,Math.min(12,vz*f));if(vz===1)vx=vy=0;applyV();}
$('vstage').addEventListener('wheel',e=>{e.preventDefault();zoomBy(e.deltaY<0?1.2:1/1.2);},{passive:false});
$('vstage').addEventListener('pointerdown',e=>{drag={x:e.clientX-vx,y:e.clientY-vy,m:false};$('vstage').setPointerCapture(e.pointerId);});
$('vstage').addEventListener('pointermove',e=>{if(!drag)return;drag.m=true;if(vz>1){vx=e.clientX-drag.x;vy=e.clientY-drag.y;applyV();}});
$('vstage').addEventListener('pointerup',e=>{const moved=drag&&drag.m;drag=null;if(!moved&&e.target===$('vstage'))closeViewer();});
$('vstage').addEventListener('dblclick',()=>zoomBy(vz>1?1/vz:3));

// ---------- albums ----------
let ALB=[];
function galItem(thumb,click,title,sub){return '<div class="it" onclick="'+click+'"><img loading="lazy" src="'+thumb+'" alt="">'+
  '<div class="cap"><b>'+esc(title)+'</b>'+(sub?' &middot; '+esc(sub):'')+'</div></div>';}
function openAlb(i){const a=ALB[i],f='/api/album_image?path='+encodeURIComponent(a.full);openViewer(f,f,[a.full,a.thn]);}
function openCap(f){openViewer(f,f+'&dl=1');}
async function loadAlbums(){
  try{const r=await (await fetch('/api/albums',{cache:'no-store'})).json();ALB=(S&&S.connected)?(r.albums||[]).slice(0,120):[];
    $('galEmpty').style.display=ALB.length?'none':'block';
    $('gal').innerHTML=ALB.map((a,i)=>galItem('/api/album_image?path='+encodeURIComponent(a.thn),'openAlb('+i+')',a.name||'',a.count?a.count+' frames':'')).join('');}catch(e){}
  try{const r=await (await fetch('/api/captures',{cache:'no-store'})).json();const c=r.captures||[];
    $('capEmpty').style.display=c.length?'none':'block';$('capInfo').textContent=c.length+' file'+(c.length===1?'':'s');
    $('capDir').textContent=c.length?('Folder: '+r.dir):'';
    $('capGal').innerHTML=c.slice(0,120).map(x=>{const f='/api/capture?f='+encodeURIComponent(x.file);
      return galItem(f,'openCap(\''+f.replace(/'/g,'%27')+'\')',x.target,x.when);}).join('');}catch(e){}}

// ---------- charts (one measure per chart; hover for values) ----------
let HIST=[],histH=6;const CH={};
$('rng').onclick=e=>{const b=e.target.closest('button');if(!b)return;histH=+b.dataset.h;
  document.querySelectorAll('#rng .btn').forEach(x=>x.classList.toggle('on',x===b));loadHistory();};
async function loadHistory(){try{const r=await (await fetch('/api/history?h='+histH,{cache:'no-store'})).json();HIST=r.points||[];}catch(e){HIST=[];}
  drawChart('ch_b','b','%',0,100,0);drawChart('ch_c','c','°C',null,null,1);drawChart('ch_f','f','',0,null,0);
  const last=k=>{for(let i=HIST.length-1;i>=0;i--)if(HIST[i][k]!=null)return HIST[i][k];return null;};
  const b=last('b'),c=last('c'),f=last('f');
  $('v_b').textContent=b!=null?b+'%':'—';$('v_c').textContent=c!=null?c.toFixed(1)+'°':'—';$('v_f').textContent=f!=null?f:'—';
  // stack rate over the last continuous hour
  const now=Date.now()/1000,rec=HIST.filter(p=>p.f!=null&&now-p.t<3600);
  if(rec.length>2&&rec[rec.length-1].t-rec[0].t>120&&rec[rec.length-1].f>=rec[0].f){
    $('k_rate').textContent=Math.round((rec[rec.length-1].f-rec[0].f)/((rec[rec.length-1].t-rec[0].t)/3600));}else $('k_rate').textContent='—';}
function drawChart(id,key,unit,fmin,fmax,dec){
  const cv=$(id),box=cv.parentElement,dpr=window.devicePixelRatio||1,W=box.clientWidth,H=box.clientHeight;if(!W)return;
  cv.width=W*dpr;cv.height=H*dpr;const x=cv.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,W,H);
  const pts=HIST.filter(p=>p[key]!=null),L=38,Rr=12,T=8,B=22,t1=Date.now()/1000,t0=t1-histH*3600;
  x.font='11px "Segoe UI",system-ui,sans-serif';x.fillStyle='#8ba0c4';
  if(!pts.length){x.textAlign='center';x.fillText('No data in this range yet',W/2,H/2);CH[id]=null;return;}
  let lo=Math.min(...pts.map(p=>p[key])),hi=Math.max(...pts.map(p=>p[key]));
  if(fmin!=null)lo=fmin;if(fmax!=null)hi=fmax;if(hi-lo<1e-6){hi+=1;lo-=fmin!=null?0:1;}
  if(fmin==null){const pad=(hi-lo)*.15;lo-=pad;hi+=pad;}else if(fmax==null)hi=Math.max(hi*1.1,hi+1);
  const X=t=>L+(t-t0)/(t1-t0)*(W-L-Rr),Y=v=>T+(1-(v-lo)/(hi-lo))*(H-T-B);
  x.strokeStyle='rgba(90,120,170,.16)';x.lineWidth=1;x.textAlign='right';x.textBaseline='middle';
  for(let i=0;i<=3;i++){const v=lo+(hi-lo)*i/3,y=Math.round(Y(v))+.5;x.beginPath();x.moveTo(L,y);x.lineTo(W-Rr,y);x.stroke();x.fillText(v.toFixed(hi-lo<6?1:0),L-6,y);}
  x.textAlign='center';x.textBaseline='alphabetic';
  for(let i=0;i<=3;i++){const t=t0+(t1-t0)*i/3;x.textAlign=i===0?'left':i===3?'right':'center';x.fillText(hm(new Date(t*1000)),X(t),H-6);}
  // line, broken across offline gaps
  const gap=Math.max(120,histH*3600/120);let segs=[],cur=[];
  HIST.forEach(p=>{if(p[key]==null||p.t<t0||(cur.length&&p.t-cur[cur.length-1].t>gap)){if(cur.length)segs.push(cur);cur=[];}if(p[key]!=null&&p.t>=t0)cur.push(p);});
  if(cur.length)segs.push(cur);
  segs.forEach(sg=>{const g=x.createLinearGradient(0,T,0,H-B);g.addColorStop(0,'rgba(110,168,255,.22)');g.addColorStop(1,'rgba(110,168,255,0)');
    x.beginPath();sg.forEach((p,i)=>i?x.lineTo(X(p.t),Y(p[key])):x.moveTo(X(p.t),Y(p[key])));
    x.strokeStyle='#6ea8ff';x.lineWidth=2;x.lineJoin='round';x.stroke();
    x.lineTo(X(sg[sg.length-1].t),H-B);x.lineTo(X(sg[0].t),H-B);x.closePath();x.fillStyle=g;x.fill();});
  const lp=pts[pts.length-1];x.beginPath();x.arc(X(lp.t),Y(lp[key]),4,0,6.28);x.fillStyle='#6ea8ff';x.fill();x.lineWidth=2;x.strokeStyle='#0c1220';x.stroke();
  CH[id]={pts,X,Y,key,unit,dec,T,B,H,redraw:()=>drawChart(id,key,unit,fmin,fmax,dec)};
  if(!cv._h){cv._h=1;cv.addEventListener('pointermove',e=>hover(id,e));cv.addEventListener('pointerleave',()=>{$('tip').style.display='none';if(CH[id])CH[id].redraw();});}}
function hover(id,e){const c=CH[id];if(!c)return;const cv=$(id),r=cv.getBoundingClientRect(),mx=e.clientX-r.left;
  let best=c.pts[0],bd=1e9;for(const p of c.pts){const d=Math.abs(c.X(p.t)-mx);if(d<bd){bd=d;best=p;}}
  c.redraw();const x=cv.getContext('2d'),px=c.X(best.t),py=c.Y(best[c.key]);
  x.strokeStyle='rgba(232,238,251,.35)';x.lineWidth=1;x.beginPath();x.moveTo(Math.round(px)+.5,c.T);x.lineTo(Math.round(px)+.5,c.H-c.B);x.stroke();
  x.beginPath();x.arc(px,py,5,0,6.28);x.fillStyle='#e8eefb';x.fill();x.lineWidth=2;x.strokeStyle='#6ea8ff';x.stroke();
  const tp=$('tip');tp.innerHTML='<b>'+Number(best[c.key]).toFixed(c.dec)+c.unit+'</b> <span>'+hm(new Date(best.t*1000))+'</span>';
  tp.style.display='block';const tw=tp.offsetWidth;tp.style.left=Math.min(innerWidth-tw-8,Math.max(8,r.left+px-tw/2))+'px';tp.style.top=(r.top+py-38)+'px';}
addEventListener('resize',()=>{if(curView==='stats')Object.values(CH).forEach(c=>c&&c.redraw());});

// ---------- alerts ----------
let notifyOn=false;try{notifyOn=localStorage.getItem('notify')==='1';}catch(e){}
const seen=new Set();let firstTick=true,actx=null;
function beep(){try{actx=actx||new (window.AudioContext||window.webkitAudioContext)();[0,.22].forEach(d=>{const o=actx.createOscillator(),g=actx.createGain();
  o.frequency.value=880;o.connect(g);g.connect(actx.destination);g.gain.setValueAtTime(.0001,actx.currentTime+d);g.gain.exponentialRampToValueAtTime(.2,actx.currentTime+d+.02);
  g.gain.exponentialRampToValueAtTime(.0001,actx.currentTime+d+.18);o.start(actx.currentTime+d);o.stop(actx.currentTime+d+.2);});}catch(e){}}
function drawBell(){$('bell').className='pill'+(notifyOn?' live':'');$('bell').innerHTML='&#128276; alerts '+(notifyOn?'on':'off');$('s_notify').textContent=notifyOn?'on':'off';}
function toggleNotify(){notifyOn=!notifyOn;try{localStorage.setItem('notify',notifyOn?'1':'0');}catch(e){}
  if(notifyOn){beep();if(window.Notification&&Notification.permission==='default')Notification.requestPermission();
    toast('Alerts on - this tab will beep'+(window.isSecureContext?' and notify':'')+' on problems','ok');}drawBell();}
drawBell();
function handleAlerts(list){
  $('alerts').innerHTML=list.map(a=>'<div class="alert '+(a.level==='bad'?'bad':'')+'"><span class="ic">'+(a.level==='bad'?'⛔':'⚠️')+'</span><div><b>'+esc(a.title)+'</b>'+esc(a.text)+'</div></div>').join('');
  const ids=new Set(list.map(a=>a.id));
  list.forEach(a=>{if(seen.has(a.id))return;seen.add(a.id);if(firstTick||a.id==='auth')return;
    toast(a.title,a.level==='bad'?'bad':'warn');
    if(notifyOn){beep();try{if(window.Notification&&Notification.permission==='granted')new Notification('Seestar: '+a.title,{body:a.text,icon:'/icon.svg',tag:a.id});}catch(e){}}});
  [...seen].forEach(id=>{if(!ids.has(id)){seen.delete(id);if(id==='offline'&&!firstTick)toast('Scope is back online','ok');}});
  firstTick=false;}

// ---------- poll ----------
function fmtHMS(s){if(s==null)return '\u2014';s=Math.max(0,Math.floor(s));const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),ss=s%60;
  return (h?h+'h ':'')+((h||m)?((m<10&&h?'0':'')+m+'m '):'')+(ss<10?'0':'')+ss+'s';}
function gb(mb){return mb==null?'\u2014':(mb/1024).toFixed(1)+' GB';}
function setTxt(id,v){const e=$(id);if(e&&e.textContent!==String(v))e.textContent=v;}
function pill(id,show,txt,cls){const e=$(id);if(!show){e.style.display='none';return;}e.style.display='';e.className='pill'+(cls?' '+cls:'');e.textContent=txt;}
const STAGE={AutoGoto:'Slewing\u2026',AutoFocus:'Autofocus\u2026',Stack:'Stacking',ContinuousExposure:'Live view',RTSP:'Live video',DarkLibrary:'Dark frames\u2026',Initialise:'Starting\u2026'};
const OPN={AutoGoto:'Slewing',AutoFocus:'Autofocus',PlateSolve:'Plate solving',DarkLibrary:'Dark frames',EqModePA:'Polar align',ScopeHome:'Parking',RecordAVI:'Recording',ViewPlan:'Plan',ScopeGoto:'Slewing',FocuserMove:'Focusing',ScopeTrack:'Tracking',Initialise:'Starting',BatchStack:'Re-stacking',WheelMove:'Filter wheel'};
const WHEEL={0:'Dark (closed)',1:'IR-cut (clear)',2:'Light-pollution'};
const MODE={star:'Stargazing',sun:'Solar',moon:'Lunar',planet:'Planetary',scenery:'Scenery'};
let imgRev=-1,serverDown=false,vidOn=false,vidStall=0;
function setVideo(want){const v=$('vid');
  if(want&&!vidOn){vidOn=true;vidStall=0;v.onerror=()=>{vidOn=false;v.style.display='none';};v.src='/api/video?cam='+(camSwap?'wide':'tele')+'&t='+Date.now();v.style.display='block';$('live').style.display='none';$('liveEmpty').style.display='none';}
  else if(!want&&vidOn){vidOn=false;v.removeAttribute('src');v.style.display='none';imgRev=-1;}}
function drawLevel(lv){const cv=$('lvl'),x=cv.getContext('2d'),c=55;x.clearRect(0,0,110,110);x.strokeStyle='rgba(90,120,170,.35)';x.lineWidth=1;
  [48,24].forEach(r=>{x.beginPath();x.arc(c,c,r,0,6.29);x.stroke();});x.beginPath();x.moveTo(c-48,c);x.lineTo(c+48,c);x.moveTo(c,c-48);x.lineTo(c,c+48);x.stroke();
  if(!lv||lv.x==null)return;const k=48/0.07,bx=Math.max(-46,Math.min(46,lv.x*k)),by=Math.max(-46,Math.min(46,lv.y*k));
  x.beginPath();x.arc(c+bx,c-by,8,0,6.29);x.fillStyle=(lv.angle!=null&&lv.angle<1)?'#39d98a':'#ffd166';x.fill();}
async function tick(){
  let d;try{d=await (await fetch('/api/state',{cache:'no-store'})).json();serverDown=false;}
  catch(e){$('conn').className='pill dead';$('conn').innerHTML='<span class="dot"></span>Studio not running';
    if(!serverDown){serverDown=true;$('alerts').innerHTML='<div class="alert bad"><span class="ic">\u26d4</span><div><b>Studio server is not responding</b>Start it again on the PC (Start Seestar Studio.bat).</div></div>';}
    document.body.classList.add('off');S=null;setVideo(false);return;}
  S=d;const on=d.connected,t=d.target||{},st=d.stack||{},ex=d.exposure||{},p=d.power||{},dk=d.disk||{},dv=d.device||{},vw=d.view||{},se=d.settings||{},mt=d.mount||{};
  document.body.classList.toggle('off',!on);
  $('conn').className='pill '+(on?'live':'dead');$('conn').innerHTML='<span class="dot'+(on?' on':'')+'"></span>'+(on?'LIVE':'scope offline');
  $('demo').style.display=d.demo?'':'none';
  setTxt('modepill',!on?'last known data':d.authed?'full control':(d.firmware_gated?'monitor only':'connecting'));
  pill('host',d.host,d.host);pill('tgt',t.name,'\u25c9 '+(t.name||''));
  const low=p.battery!=null&&p.battery<=20&&!p.charging;
  pill('batt',p.battery!=null,(p.charging?'\u26a1 ':'\ud83d\udd0b ')+p.battery+'%'+(on?'':' (last)'),on&&low?(p.battery<=10?'dead':'warn'):'');
  pill('temp',d.temp!=null,(d.temp!=null?d.temp.toFixed(1):'')+'\u00b0C');
  handleAlerts(d.alerts||[]);

  // ----- live -----
  const stage=on?vw.stage:null,idle=!on||vw.state==='idle'||!vw.state,stacking=stage==='Stack';
  const wantVid=on&&(stage==='RTSP'||stage==='ContinuousExposure')&&d.video&&d.video.available;if(stage!=='RTSP'&&camSwap){camSwap=false;setVideo(false);}setVideo(wantVid);setWide(wantVid&&stage==='RTSP'&&!!(d.video_wide&&d.video_wide.available));renderSkyline(d);
  if(vidOn){vidStall=(d.video.live&&$('vid').naturalWidth>0)?0:vidStall+1;if(vidStall>(d.video.live?4:14)){setVideo(false);}}
  const vmode=on&&!idle&&t.mode&&t.mode!=='star';
  setTxt('c_stacked',vmode?'\u2014':st.stacked_frame!=null?st.stacked_frame:'\u2014');
  const tot=vmode?0:(st.stacked_frame||0)+(st.dropped_frame||0);
  setTxt('c_dropped',vmode?'not stacking in this mode':'dropped '+(st.dropped_frame!=null?st.dropped_frame:'\u2014')+(tot?' \u00b7 '+Math.round(100*(st.stacked_frame||0)/tot)+'% kept':''));
  setTxt('c_integ',vmode?'\u2014':fmtHMS(d.integration_s));
  setTxt('c_integsub',vmode?'\u2014':(st.stacked_frame!=null&&ex.exp_ms)?(st.stacked_frame+' \u00d7 '+(ex.exp_ms/1000)+'s'):'\u2014');
  setTxt('c_exp',!on?'offline':idle?(mt.close?'parked':'idle'):(STAGE[stage]||stage||'working').replace('\u2026',''));
  setTxt('c_expsub',!on?'\u2014':idle?'no view running':((MODE[t.mode]||t.mode||'')+(ex.exp_ms&&t.mode==='star'?' \u00b7 '+(ex.exp_ms/1000)+'s subs':'')+(ex.gain!=null?' \u00b7 gain '+ex.gain:'')));
  setTxt('c_batt',p.battery!=null?p.battery+'%':'\u2014');
  setTxt('c_battsub',!on?'last reading before it went offline':p.charging?'on external power':
    d.battery_hours_left!=null?('about '+fmtHMS(d.battery_hours_left*3600).replace(/ \d+s$/,'')+' left \u00b7 '+d.battery_rate+'%/h'):'on battery \u00b7 estimating\u2026');
  setTxt('liveTgt',vmode?(MODE[t.mode]||t.mode):(t.name||''));
  const now=Date.now()/1000,pills=[];if(stage)pills.push(STAGE[stage]||stage);
  if(on)for(const k in (d.ops||{})){const o=d.ops[k];if(o.state==='working'&&now-o.t<900&&OPN[k]&&!pills.some(x=>x.startsWith(OPN[k].slice(0,5))))pills.push(OPN[k]+'\u2026');}
  if(on&&d.plan&&d.plan.state==='working')pills.push('Plan running');
  $('opsPills').innerHTML=pills.map(x=>'<span class="pill" style="background:rgba(0,0,0,.6);margin-left:6px">'+esc(x)+'</span>').join('');
  $('bStack').style.display=(stacking||(on&&!idle&&t.mode&&t.mode!=='star'))?'none':'';$('bStopStack').style.display=stacking?'':'none';
  $('bRec').style.display=(stage==='RTSP'||recOn)?'':'none';$('bSnap').style.display=vidOn?'':'none';
  if(on&&t.mode&&!idle&&document.activeElement!==$('viewMode'))$('viewMode').value=t.mode;

  // ----- camera -----
  setTxt('g_cur',ex.gain!=null?ex.gain:'\u2014');
  const sl=se.exp_ms&&se.exp_ms.stack_l;setTxt('e_cur',sl?(sl/1000)+' s':(ex.exp_ms?(ex.exp_ms/1000)+' s':'\u2014'));
  setTxt('wheelCur',d.wheel!=null?(WHEEL[d.wheel]||d.wheel):((d.filter&&d.filter.lp!=null)?(d.filter.lp?'Light-pollution':'IR-cut (clear)'):'\u2014'));
  [0,1,2].forEach(i=>$('w'+i).classList.toggle('on',on&&d.wheel===i));
  const dz=se.stack_dither||{};fill('d_pix',dz.pix);fill('d_int',dz.interval);
  if(se.isp_exp_ms>0)fill('isp_exp',se.isp_exp_ms);if(se.isp_gain>=0)fill('isp_gain',se.isp_gain);
  if(se.ae_bri_percent!=null&&document.activeElement!==$('ae')){$('ae').value=se.ae_bri_percent;$('aeLbl').textContent=Math.round(se.ae_bri_percent);}
  if(se.beep_volume!=null&&document.activeElement!==$('s_vol')){const sv=$('s_vol');if(![...sv.options].some(o=>o.value===String(se.beep_volume)))sv.add(new Option(String(se.beep_volume),String(se.beep_volume)));sv.value=String(se.beep_volume);}
  syncToggles();

  // ----- mount / focus -----
  setTxt('m_ra',t.ra!=null?t.ra.toFixed(4)+' h':'\u2014');setTxt('m_dec',t.dec!=null?t.dec.toFixed(4)+'\u00b0':'\u2014');
  const loc=getLoc(),az=d.altaz;
  setTxt('m_alt',az&&az.alt!=null?(az.alt.toFixed(1)+'\u00b0 / '+az.az.toFixed(1)+'\u00b0'):(loc&&t.ra!=null)?altOf(t.ra,t.dec,loc).toFixed(1)+'\u00b0 (computed)':'\u2014');
  setTxt('m_arm',!on?'\u2014':mt.close==null?'\u2014':mt.close?'closed (parked)':'open');
  setTxt('m_track',!on||d.tracking==null?'\u2014':d.tracking?'on':'off');
  setTxt('m_eq',!on||mt.equ_mode==null?'\u2014':mt.equ_mode?'Equatorial':'Alt-Az');
  const pa=(d.ops||{}).EqModePA;setTxt('m_pa',pa&&pa.total!=null?(pa.total.toFixed(2)+'\u00b0'+(pa.x!=null?' (az '+pa.x.toFixed(2)+'\u00b0, alt '+pa.y.toFixed(2)+'\u00b0)':'')):pa&&pa.state?pa.state:'\u2014');
  const sv=d.solve;setTxt('m_solve',sv&&sv.ra_dec?('RA '+sv.ra_dec[0].toFixed(4)+' h, Dec '+sv.ra_dec[1].toFixed(3)+'\u00b0'):sv&&sv.error?String(sv.error):'\u2014');
  setTxt('m_solve2',sv&&sv.fov?(sv.fov[0].toFixed(2)+'\u00b0 \u00d7 '+sv.fov[1].toFixed(2)+'\u00b0'+(sv.angle!=null?' \u00b7 '+sv.angle.toFixed(1)+'\u00b0':'')):'\u2014');
  const lv=d.level;setTxt('m_tilt',lv&&lv.angle!=null?lv.angle.toFixed(2)+'\u00b0':'\u2014');if(curView==='mount')drawLevel(on?lv:null);
  setTxt('m_comp',d.compass&&d.compass.direction!=null?d.compass.direction.toFixed(0)+'\u00b0':'\u2014');
  setTxt('focPos',d.focus&&d.focus.position!=null?d.focus.position:'\u2014');
  setTxt('dewCur',d.heater==null&&se.heater_enable==null?'\u2014':(d.heater||se.heater_enable)?'ON':'OFF');

  // ----- settings -----
  setTxt('s_model',dv.model||'\u2014');setTxt('s_fw',dv.firmware||'\u2014');setTxt('s_sn',dv.sn||'\u2014');
  setTxt('s_disk',gb(dk.free_mb)+(dk.total_mb?(' / '+gb(dk.total_mb)):''));
  const wf=d.wifi;setTxt('s_wifi',on&&wf&&wf.ssid?(wf.ssid+(wf.sig_lev!=null?' \u00b7 '+wf.sig_lev+' dBm':'')+(wf.freq?(wf.freq>4000?' \u00b7 5 GHz':' \u00b7 2.4 GHz'):'')):'\u2014');
  setTxt('s_auth',d.authed?'authenticated':(on?(d.firmware_gated?'locked (no key)':'open'):'\u2014'));
  setTxt('s_seen',on?'now':(d.last_seen||'never'));
  setTxt('s_sloc',d.location&&d.location.lat!=null?(d.location.lat.toFixed(3)+'\u00b0, '+d.location.lon.toFixed(3)+'\u00b0'):'\u2014');
  const au=d.autosave||{};setTxt('s_auto',au.minutes?('every '+au.minutes+' min'):'off');setTxt('s_lastcap',au.last||'\u2014');
  setTxt('k_saves',au.count!=null?au.count:'\u2014');setTxt('k_savesub',au.minutes?('full-res copy every '+au.minutes+' min'):'auto-save is off');
  setTxt('k_keep',tot?Math.round(100*(st.stacked_frame||0)/tot)+'%':'\u2014');setTxt('k_keepsub',tot?((st.stacked_frame||0)+' kept, '+(st.dropped_frame||0)+' dropped'):'accepted vs dropped');
  setTxt('k_drain',d.battery_rate!=null?d.battery_rate+'%':'\u2014');
  setTxt('k_drainsub',d.battery_hours_left!=null?('per hour \u00b7 ~'+d.battery_hours_left.toFixed(1)+' h left'):'per hour');
  showLoc();if(curView==='plan')renderRun();

  // ----- image -----
  const im=d.image||{};$('frame').classList.toggle('stale',!!im.stale);
  if(vidOn){setTxt('liveLabel',stage==='RTSP'?'Live video':'Live view (unstacked)');setTxt('liveUpd',d.video.live?'streaming':(d.video.error||'connecting to the video feed\u2026'));}
  else if(im.available){if(im.rev!==imgRev){imgRev=im.rev;const el=$('live');
      el.onload=()=>{if(!vidOn){el.style.display='block';$('liveEmpty').style.display='none';}};el.src='/api/image?kind=thumb&v='+im.rev+'_'+Date.now();}
    setTxt('liveLabel',im.label||'');setTxt('liveUpd',im.stale?('last image '+(im.updated||'')+' \u00b7 scope offline'):(im.updated?('updated '+im.updated):''));}
  else setTxt('liveEmpty',on?'No image yet \u2014 start a view, or GoTo a target from the Targets tab.':'Scope offline \u2014 the live image will appear here when it reconnects.');
  document.title=(on?(stacking&&st.stacked_frame!=null?'('+st.stacked_frame+') ':'')+(t.name||'Seestar'):'\u26a0 offline')+' \u2014 Seestar Studio';
  if(curView==='console')drawLog();
}
let n=0;
setInterval(()=>{if(document.hidden&&!notifyOn)return;tick();n++;if(curView==='target'&&n%4===0)drawSky();if(n%20===0){if(curView==='stats')loadHistory();if(curView==='target')renderPlanner();if(curView==='albums')loadAlbums();if(curView==='plan')renderPlan();}},1600);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});
let tab0='live';try{tab0=localStorage.getItem('tab')||'live';}catch(e){}
tick().then(()=>sel(NAV.some(x=>x[0]===tab0)?tab0:'live'));
</script>
</body>
</html>
"""
