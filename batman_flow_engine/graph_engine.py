import json
import pathlib
import webbrowser

data = json.loads(pathlib.Path("storage/latest.json").read_text())
equities = data.get("equities", {})
crypto = data.get("crypto", {})
dq = data.get("dq", {})
regime = data.get("stress", {}).get("regime", {})
narrative = data.get("narrative", {})
regime_label = regime.get("label", "UNKNOWN")
regime_color = (
    "#FF0055" if regime_label in ["STRESS", "DATA_DEGRADED"] else "#FF6600" if regime_label == "TENSION" else "#00FF88"
)

hot = sorted(
    [(s, v) for s, v in equities.items() if (v.get("vol_z") or 0) >= 2.5 and v.get("status", "").startswith("ok")],
    key=lambda x: x[1].get("vol_z", 0),
    reverse=True,
)

nodes, edges = [], []


def node(id, label, color, size, group, details="", shape="hexagon"):
    nodes.append(
        {
            "id": id,
            "label": label,
            "color": {
                "background": color + "22",
                "border": color,
                "highlight": {"background": color + "44", "border": "#FFFFFF"},
            },
            "size": size,
            "group": group,
            "title": details,
            "shape": shape,
            "font": {"color": color, "size": 11, "face": "Courier New", "bold": True},
            "borderWidth": 2,
            "shadow": {"enabled": True, "color": color, "size": 15, "x": 0, "y": 0},
        }
    )


def edge(src, dst, label="", color="#00FF88", width=1):
    edges.append(
        {
            "from": src,
            "to": dst,
            "label": label,
            "color": {"color": color + "88", "highlight": color},
            "width": width,
            "font": {"color": color + "AA", "size": 9, "face": "Courier New"},
            "arrows": {"to": {"enabled": True, "scaleFactor": 0.6}},
            "smooth": {"type": "continuous"},
        }
    )


node(
    "ENGINE",
    "🦇 BATMAN\nFLOW ENGINE",
    "#FFD700",
    55,
    "core",
    f"<b style='color:#FFD700'>BATMAN FLOW ENGINE</b><br><span style='color:#00FF88'>Régimen: {regime_label}</span><br>DQ: {dq.get('overall_status')}<br>eq_ratio: {dq.get('equities_ok_ratio')}<br>Hits: {narrative.get('total_hits',0)}",
    "dot",
)
node(
    "REGIME",
    f"⚡ {regime_label}",
    regime_color,
    35,
    "regime",
    f"<b style='color:{regime_color}'>RÉGIMEN: {regime_label}</b><br>Triggers: {regime.get('triggers')}",
)
edge("ENGINE", "REGIME", "régimen", regime_color, 3)
node(
    "WAR",
    "☢️ IRAN\nVS USA",
    "#FF0055",
    42,
    "geo",
    "<b style='color:#FF0055'>SHOCK GEOPOLÍTICO</b><br>Guerra Iran vs USA<br>Impacto: energía, FX,<br>aerolíneas, refugio",
)
edge("WAR", "REGIME", "macro shock", "#FF0055", 4)

war_map = {
    "XLE": ("⚡ XLE\nENERGÍA", "#FF6600", "SUBE — guerra = petróleo"),
    "GLD": ("💎 GLD\nORO", "#FFD700", "SUBE — refugio seguro"),
    "TLT": ("📡 TLT\nBONOS", "#00AAFF", "SUBE — huida calidad"),
    "UAL": ("💀 UAL\nAIRLINES", "#FF0055", "BAJA — riesgo viajes"),
    "DAL": ("💀 DAL\nAIRLINES", "#FF0055", "BAJA — riesgo viajes"),
    "XLK": ("🔮 XLK\nTECH", "#AA44FF", "NEUTRAL/BAJA"),
    "XLF": ("🏦 XLF\nFINANCE", "#00AAFF", "DEPENDE de rates"),
}
for sym, (lbl, col, razon) in war_map.items():
    eq = equities.get(sym, {})
    vz = eq.get("vol_z") or 0
    r1d = eq.get("ret1d") or 0
    px = eq.get("px") or 0
    det = f"<b style='color:{col}'>{sym}</b><br>px: ${px:.2f}<br>ret1d: <span style='color:{'#00FF88' if r1d>0 else '#FF0055'}'>{r1d:.2%}</span><br>vol_z: {vz:.2f}<br><br>{razon}"
    node(sym, f"{lbl}\nvz={vz:.1f}", col, 18 + min(abs(vz) * 4, 20), "equity", det)
    edge("WAR", sym, f"{r1d:.1%}", col, max(1, int(abs(vz))))

node(
    "FIFA",
    "⚽ FIFA\n2026",
    "#00FF88",
    38,
    "fifa",
    f"<b style='color:#00FF88'>FIFA WORLD CUP 2026</b><br>Sedes: CDMX, GDL, MTY<br>Narrative hits: {narrative.get('total_hits',0)}",
)
edge("ENGINE", "FIFA", "narrativa", "#00FF88", 2)
edge("WAR", "FIFA", "riesgo seguridad", "#FF6600", 3)

for cid, lbl, det in [
    ("CDMX", "🌆 CDMX", "Estadio Azteca | $800M USD"),
    ("GDL", "🌆 GDL", "Estadio Akron | 500K visitantes"),
    ("MTY", "🌆 MTY", "Estadio BBVA | Frontera norte"),
]:
    node(cid, lbl, "#00FF88", 26, "city", f"<b style='color:#00FF88'>{lbl}</b><br>Sede FIFA 2026<br>{det}")
    edge("FIFA", cid, "sede", "#00FF88", 2)
    edge("WAR", cid, "riesgo", "#FF6600", 1)

node(
    "CRYPTO",
    "₿ CRYPTO\nLIQUIDEZ",
    "#AA44FF",
    30,
    "crypto",
    "<b style='color:#AA44FF'>CRYPTO MARKETS</b><br>BTC/ETH/SOL<br>Correlación macro stress",
)
edge("ENGINE", "CRYPTO", "liquidez", "#AA44FF", 2)
edge("WAR", "CRYPTO", "flight to BTC?", "#AA44FF", 2)

for sym, v in crypto.items():
    if v.get("status") == "ok":
        px = v.get("px") or 0
        ret = v.get("ret_1h") or 0
        rv = v.get("rv_ann") or 0
        col = "#00FF88" if ret > 0.02 else "#FF0055" if ret < -0.02 else "#AA44FF"
        node(
            sym,
            f"{sym}\n{ret:.2%}",
            col,
            22,
            "crypto",
            f"<b style='color:{col}'>{sym}</b><br>px: ${px:,.2f}<br>ret_1h: {ret:.2%}<br>rv_ann: {rv:.2%}",
        )
        edge("CRYPTO", sym, f"{ret:.1%}", col, 2)

node(
    "NARRATIVE",
    f"📡 NARRATIVA\n{narrative.get('total_hits',0)} HITS",
    "#00CCFF",
    28,
    "narrative",
    f"<b style='color:#00CCFF'>NARRATIVE INTEL</b><br>Hits: {narrative.get('total_hits',0)}<br>FIFA+Guerra+Seguridad",
)
edge("ENGINE", "NARRATIVE", "intel", "#00CCFF", 2)
edge("NARRATIVE", "FIFA", "cobertura", "#00CCFF", 2)
edge("NARRATIVE", "WAR", "seguridad", "#FF0055", 2)

dq_col = "#00FF88" if not dq.get("breaker_triggered") else "#FF0055"
node(
    "DQ",
    f"🛡️ DQ\n{dq.get('overall_status','?').upper()}",
    dq_col,
    22,
    "dq",
    f"<b style='color:{dq_col}'>DATA QUALITY</b><br>Status: {dq.get('overall_status')}<br>eq_ratio: {dq.get('equities_ok_ratio')}<br>breaker: {dq.get('breaker_triggered')}",
)
edge("ENGINE", "DQ", "calidad", dq_col, 2)

node(
    "HOT",
    f"🔥 HOT\n{len(hot)} ASSETS",
    "#FF6600",
    30,
    "hot",
    "<b style='color:#FF6600'>HOT ASSETS</b><br>vol_z >= 2.5<br>"
    + "<br>".join([f"{s}: {v.get('vol_z',0):.1f}" for s, v in hot[:5]]),
)
edge("ENGINE", "HOT", "anomalías", "#FF6600", 3)
for s, v in hot[:8]:
    if s not in war_map:
        vz = v.get("vol_z") or 0
        r1d = v.get("ret1d") or 0
        px = v.get("px") or 0
        node(
            s,
            f"🔥 {s}\nvz={vz:.1f}",
            "#FF6600",
            16 + min(vz * 3, 15),
            "hot",
            f"<b style='color:#FF6600'>{s}</b><br>px: ${px:.2f}<br>vol_z: {vz:.2f}<br>ret1d: {r1d:.2%}",
        )
        edge("HOT", s, f"{r1d:.1%}", "#FF6600", 2)

nodes_j = json.dumps(nodes)
edges_j = json.dumps(edges)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>🦇 Batman Flow Engine — CYBERPUNK</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:#020408;color:#00FF88;font-family:'Share Tech Mono',monospace;overflow:hidden}}
  #scanlines{{position:fixed;top:0;left:0;width:100%;height:100%;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.05) 2px,rgba(0,0,0,0.05) 4px);pointer-events:none;z-index:999}}
  #header{{padding:10px 20px;background:#020408;border-bottom:1px solid #00FF8844;display:flex;justify-content:space-between;align-items:center;position:relative}}
  #header::after{{content:'';position:absolute;bottom:0;left:0;width:100%;height:1px;background:linear-gradient(90deg,transparent,#00FF88,#AA44FF,transparent)}}
  h1{{font-size:14px;color:#00FF88;text-shadow:0 0 10px #00FF88;letter-spacing:3px}}
  #controls{{display:flex;gap:8px;align-items:center}}
  #search{{background:#020408;border:1px solid #00FF8866;color:#00FF88;padding:5px 10px;border-radius:2px;font-family:monospace;font-size:11px;outline:none}}
  #search:focus{{border-color:#00FF88;box-shadow:0 0 8px #00FF8844}}
  .btn{{background:#020408;border:1px solid #00FF8866;color:#00FF88;padding:5px 10px;border-radius:2px;cursor:pointer;font-size:11px;font-family:monospace;transition:all 0.2s}}
  .btn:hover{{background:#00FF8822;border-color:#00FF88;box-shadow:0 0 8px #00FF8844}}
  #stats{{display:flex;gap:24px}}
  .stat{{text-align:center}}
  .stat-val{{font-size:16px;font-weight:bold;text-shadow:0 0 8px currentColor}}
  .stat-lbl{{font-size:9px;color:#00FF8877;letter-spacing:2px}}
  #container{{display:flex;height:calc(100vh - 52px)}}
  #graph{{flex:1;background:radial-gradient(ellipse at center,#020c14 0%,#020408 70%)}}
  #panel{{width:280px;background:#020408;border-left:1px solid #00FF8822;padding:14px;overflow-y:auto;display:flex;flex-direction:column;gap:10px}}
  .panel-section{{border:1px solid #00FF8822;border-radius:2px;padding:10px}}
  .panel-title{{font-size:10px;letter-spacing:3px;color:#00FF8877;margin-bottom:8px;text-transform:uppercase}}
  #node-detail{{font-size:11px;line-height:1.9;min-height:80px;color:#00FF88AA}}
  .regime-box{{padding:8px;text-align:center;font-size:13px;font-weight:bold;letter-spacing:2px;border:1px solid {regime_color};color:{regime_color};text-shadow:0 0 10px {regime_color};box-shadow:0 0 15px {regime_color}22}}
  .leg-item{{display:flex;align-items:center;gap:8px;font-size:10px;margin:3px 0;color:#00FF88AA}}
  .leg-dot{{width:10px;height:10px;border-radius:1px;flex-shrink:0;box-shadow:0 0 6px currentColor}}
  .hot-item{{font-size:10px;color:#FF6600AA;margin:2px 0;padding:2px 0;border-bottom:1px solid #FF660011}}
  #grid{{position:fixed;top:0;left:0;width:100%;height:100%;background-image:linear-gradient(#00FF8808 1px,transparent 1px),linear-gradient(90deg,#00FF8808 1px,transparent 1px);background-size:40px 40px;pointer-events:none;z-index:0}}
</style>
</head>
<body>
<div id="grid"></div>
<div id="scanlines"></div>
<div id="header">
  <h1>[ 🦇 BATMAN FLOW ENGINE // SYSTEMIC RISK GRAPH // LIVE ]</h1>
  <div id="controls">
    <input id="search" type="text" placeholder="// SEARCH NODE..." oninput="searchNode(this.value)">
    <button class="btn" onclick="resetView()">[ RESET ]</button>
    <button class="btn" onclick="togglePhysics()">[ PHYSICS ]</button>
  </div>
  <div id="stats">
    <div class="stat"><div class="stat-val" style="color:{regime_color};text-shadow:0 0 8px {regime_color}">{regime_label}</div><div class="stat-lbl">RÉGIMEN</div></div>
    <div class="stat"><div class="stat-val" style="color:#00FF88">{dq.get('equities_ok_ratio',0):.0%}</div><div class="stat-lbl">DQ RATIO</div></div>
    <div class="stat"><div class="stat-val" style="color:#00CCFF">{narrative.get('total_hits',0)}</div><div class="stat-lbl">HITS</div></div>
    <div class="stat"><div class="stat-val" style="color:#FF6600">{len(hot)}</div><div class="stat-lbl">HOT</div></div>
  </div>
</div>
<div id="container">
  <div id="graph"></div>
  <div id="panel">
    <div class="regime-box">⚡ RÉGIMEN: {regime_label}</div>
    <div class="panel-section">
      <div class="panel-title">>> NODE DATA</div>
      <div id="node-detail">// Click en cualquier nodo<br>// para ver datos en tiempo real</div>
    </div>
    <div class="panel-section">
      <div class="panel-title">>> LEYENDA</div>
      <div class="leg-item"><div class="leg-dot" style="background:#FFD700;color:#FFD700"></div>Motor Central</div>
      <div class="leg-item"><div class="leg-dot" style="background:#FF0055;color:#FF0055"></div>Geopolítica / Guerra</div>
      <div class="leg-item"><div class="leg-dot" style="background:#00FF88;color:#00FF88"></div>FIFA 2026 / Ciudades</div>
      <div class="leg-item"><div class="leg-dot" style="background:#FF6600;color:#FF6600"></div>Energía / HOT Assets</div>
      <div class="leg-item"><div class="leg-dot" style="background:#FFD700;color:#FFD700"></div>Oro / Refugio</div>
      <div class="leg-item"><div class="leg-dot" style="background:#FF0055;color:#FF0055"></div>Aerolíneas / Riesgo</div>
      <div class="leg-item"><div class="leg-dot" style="background:#AA44FF;color:#AA44FF"></div>Crypto</div>
      <div class="leg-item"><div class="leg-dot" style="background:#00CCFF;color:#00CCFF"></div>Narrativa Intel</div>
    </div>
    <div class="panel-section">
      <div class="panel-title">>> HOT ASSETS</div>
      {"".join([f'<div class="hot-item">🔥 {s} // vol_z={v.get("vol_z",0):.2f} // ret={v.get("ret1d",0):.2%}</div>' for s,v in hot[:8]])}
    </div>
  </div>
</div>
<script>
const nodes=new vis.DataSet({nodes_j});
const edges=new vis.DataSet({edges_j});
const options={{
  physics:{{stabilization:{{iterations:300}},barnesHut:{{gravitationalConstant:-4000,springLength:160,springConstant:0.04}}}},
  edges:{{smooth:{{type:"continuous"}},font:{{color:"#00FF8866",size:9,face:"Courier New"}}}},
  nodes:{{font:{{face:"Courier New"}}}},
  interaction:{{hover:true,tooltipDelay:50,zoomView:true,dragView:true}}
}};
const network=new vis.Network(document.getElementById("graph"),{{nodes,edges}},options);
let physicsOn=true;
network.on("click",function(p){{
  if(p.nodes.length>0){{
    const n=nodes.get(p.nodes[0]);
    document.getElementById("node-detail").innerHTML=n.title||("<b>"+n.label+"</b>");
  }}
}});
network.on("hoverNode",function(p){{
  document.body.style.cursor="pointer";
}});
network.on("blurNode",function(){{
  document.body.style.cursor="default";
}});
function searchNode(v){{
  if(!v){{network.unselectAll();return;}}
  const f=nodes.get({{filter:n=>n.label.toLowerCase().includes(v.toLowerCase())}});
  if(f.length>0){{network.selectNodes([f[0].id]);network.focus(f[0].id,{{scale:1.8,animation:true}});}}
}}
function resetView(){{network.fit({{animation:true}});}}
function togglePhysics(){{physicsOn=!physicsOn;network.setOptions({{physics:{{enabled:physicsOn}}}});}}
</script>
</body>
</html>"""

pathlib.Path("batman_graph.html").write_text(html, encoding="utf-8")
print("✅ Grafo CYBERPUNK listo")
webbrowser.open(f"file://{pathlib.Path('batman_graph.html').resolve()}")
