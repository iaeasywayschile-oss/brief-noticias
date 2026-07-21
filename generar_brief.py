#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera el brief de noticias, lo guarda en archivo/ y regenera la portada.

Uso:
    python generar_brief.py            -> modo automatico (domingo = semanal)
    python generar_brief.py diario
    python generar_brief.py semanal

Necesita la variable de entorno ANTHROPIC_API_KEY.
"""

import os
import re
import sys
import json
import glob
import html
import datetime
import zoneinfo

import anthropic

MODELO = "claude-opus-4-8"
TZ = zoneinfo.ZoneInfo("America/Santiago")
RAIZ = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(RAIZ, "archivo")

# --------------------------------------------------------------------------
# Esquema que le pedimos al modelo
# --------------------------------------------------------------------------

ESQUEMA = """
{
  "fecha": "AAAA-MM-DD",
  "corte": "HH:MM CLT",
  "cobertura": "texto corto del rango cubierto",
  "resumen_5yo": "texto",
  "indicadores": [
    {"nombre": "", "valor": "", "var": "", "dir": "up|down|flat|na", "lectura": ""}
  ],
  "advertencias": ["texto de cada dato en disputa o sin confirmar"],
  "bloques": [
    {
      "id": "global|chile|argentina|semana",
      "titulo": "Global",
      "nota": "opcional: honestidad sobre la calidad del bloque, o cadena vacia",
      "noticias": [
        {
          "titulo": "",
          "que_paso": "",
          "contexto": "",
          "por_que_importa": "",
          "que_mirar": "",
          "categorias": ["Economia"],
          "flags": ["fuente_unica", "en_desarrollo"],
          "fuentes": [{"medio": "", "url": ""}]
        }
      ]
    }
  ],
  "interes_comun": {
    "titulo": "", "que_paso": "", "contexto": "", "por_que_importa": "",
    "categorias": ["Ciencia"], "flags": [], "fuentes": [{"medio": "", "url": ""}]
  },
  "seguimiento": {
    "nota": "",
    "items": [{"titulo": "", "cambio": "", "estado": "Avanza|Se estanca|Se revierte|Cerrada", "url": ""}],
    "abiertas": ["titulo de cada historia que sigue abierta"]
  },
  "agenda": [{"fecha": "Mie 22 jul", "pais": "CHILE", "texto": "", "clave": true}]
}
"""

SISTEMA = (
    "Sos un periodista senior que arma un brief de noticias verificado. "
    "Usa la busqueda web de forma intensiva: escala la cantidad de busquedas a la "
    "complejidad, entre 15 y 30 por brief. Nunca completes con memoria lo que no "
    "pudiste verificar. Devolve exclusivamente JSON valido, sin markdown."
)


def construir_prompt(modo, corte_anterior, contexto_previo):
    archivo_prompt = "PROMPT_SEMANAL.md" if modo == "semanal" else "PROMPT.md"
    with open(os.path.join(RAIZ, archivo_prompt), encoding="utf-8") as f:
        base = f.read()

    ahora = datetime.datetime.now(TZ)
    partes = [base, "\n\n---\n\n## DATOS DE ESTA EJECUCION\n"]
    partes.append(f"- Fecha y hora actual: {ahora.strftime('%A %d de %B de %Y, %H:%M')} (hora de Chile).")
    if corte_anterior:
        partes.append(f"- Corte del brief anterior: {corte_anterior}. Cubri desde ahi hasta ahora.")
    else:
        partes.append("- No hay brief anterior. Cubri las ultimas 24 horas y decilo en el campo cobertura.")

    if contexto_previo:
        partes.append("\n### Material de los briefs anteriores\n")
        partes.append("Usalo como memoria para el bloque Seguimiento. Verifica de nuevo toda cifra antes de repetirla.\n")
        partes.append("```json\n" + contexto_previo + "\n```")

    partes.append("\n### Esquema JSON exacto que tenes que devolver\n")
    partes.append("```json" + ESQUEMA + "```")
    partes.append(
        "\nRespond**e unicamente con el JSON**. Sin texto antes ni despues. "
        "Sin ```json alrededor. El campo fecha debe ser " + ahora.strftime("%Y-%m-%d") + "."
    )
    return "\n".join(partes)


def resumen_para_seguimiento(datos, dias):
    """Version condensada de briefs previos, para no gastar contexto de mas."""
    salida = []
    for d in datos[-dias:]:
        item = {
            "fecha": d.get("fecha"),
            "corte": d.get("corte"),
            "titulares": [],
            "abiertas": d.get("seguimiento", {}).get("abiertas", []),
        }
        for b in d.get("bloques", []):
            for n in b.get("noticias", []):
                item["titulares"].append({
                    "bloque": b.get("id"),
                    "titulo": n.get("titulo"),
                    "que_mirar": n.get("que_mirar", ""),
                })
        salida.append(item)
    return json.dumps(salida, ensure_ascii=False, indent=1)


def pedir_brief(modo, corte_anterior, contexto_previo):
    cliente = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    respuesta = cliente.messages.create(
        model=MODELO,
        max_tokens=32000,
        system=SISTEMA,
        messages=[{"role": "user", "content": construir_prompt(modo, corte_anterior, contexto_previo)}],
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 30}],
    )
    texto = "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")
    texto = re.sub(r"^\s*```(?:json)?|```\s*$", "", texto.strip())
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin == -1:
        raise ValueError("El modelo no devolvio JSON. Primeros 500 caracteres:\n" + texto[:500])
    return json.loads(texto[inicio:fin + 1])


# --------------------------------------------------------------------------
# Render HTML
# --------------------------------------------------------------------------

CSS = """
:root{
  --ink:#0d1117;--ink2:#161b22;--line:#2a323d;--line2:#39424f;
  --txt:#dfe4ec;--dim:#8b95a5;--dimmer:#5e6875;
  --up:#3fb950;--down:#f85149;--flag:#d29922;--key:#58a6ff;
}
*{box-sizing:border-box}
body{background:var(--ink);color:var(--txt);margin:0;
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px;line-height:1.6}
.page{max-width:900px;margin:0 auto;border-left:1px solid var(--line);border-right:1px solid var(--line);min-height:100vh}
.mono,header .meta,nav a,h2,.lbl,.rank,td.v,.agenda .d,.agenda .c,footer{
  font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
header{padding:24px;border-bottom:1px solid var(--line);background:var(--ink2)}
h1{font-size:20px;margin:0 0 7px;font-weight:650;letter-spacing:-.01em}
header .meta{font-size:12px;color:var(--dim);letter-spacing:.02em}
header .meta b{color:var(--txt);font-weight:600}
.pill{display:inline-block;font-size:10px;letter-spacing:.1em;text-transform:uppercase;
  border:1px solid var(--line2);color:var(--flag);padding:2px 8px;border-radius:3px;margin-bottom:9px}
nav{display:flex;flex-wrap:wrap;border-bottom:1px solid var(--line);background:var(--ink2)}
nav a{padding:9px 14px;font-size:12px;color:var(--dim);text-decoration:none;
  border-right:1px solid var(--line);letter-spacing:.03em;text-transform:uppercase}
nav a:hover{color:var(--txt);background:#1c2330}
nav a:focus-visible{outline:2px solid var(--key);outline-offset:-2px}
main{padding:0 24px 40px}
section{padding-top:34px;scroll-margin-top:10px}
h2{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);font-weight:600;
  margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h2 span{color:var(--dimmer);letter-spacing:.02em;text-transform:none;font-weight:400}
.fiveyo{background:#12181f;border:1px solid var(--line);border-left:3px solid var(--key);
  padding:16px 18px;border-radius:4px;font-size:15.5px;color:#e8edf5}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--dimmer);
  font-weight:600;padding:6px 10px 6px 0;border-bottom:1px solid var(--line);
  font-family:ui-monospace,Menlo,Consolas,monospace}
td{padding:9px 10px 9px 0;border-bottom:1px solid #1e242d;vertical-align:top}
td.v{white-space:nowrap}
.up{color:var(--up)}.down{color:var(--down)}.flat,.na{color:var(--dim)}
td.read{color:var(--dim);font-size:12.5px;line-height:1.45}
details{border:1px solid var(--line);border-radius:4px;margin-bottom:10px;background:#11161d}
details[open]{border-color:var(--line2)}
summary{padding:13px 16px;cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
summary:focus-visible{outline:2px solid var(--key);outline-offset:-2px}
.ttl{font-size:16px;font-weight:600;line-height:1.35;margin-bottom:6px;display:flex;gap:9px;align-items:baseline}
.rank{font-size:12px;color:var(--dimmer);flex:0 0 auto;padding-top:2px}
.why{font-size:13.5px;color:#b6c0cd;line-height:1.5;padding-left:24px}
.why b{color:var(--txt);font-weight:600}
.body{padding:0 16px 16px 40px;border-top:1px solid #1e242d;margin-top:2px}
.fld{margin-top:12px}
.lbl{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dimmer);display:block;margin-bottom:3px}
.fld p{margin:0;font-size:14px;line-height:1.58}
.src a{color:var(--key);text-decoration:none;font-size:12.5px;border-bottom:1px solid #23405e}
.src a:hover{border-bottom-color:var(--key)}
.src span.sep{color:var(--dimmer);padding:0 6px}
.tags{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 0 24px}
.tag{font-size:10px;letter-spacing:.08em;text-transform:uppercase;padding:2px 7px;border-radius:3px;
  border:1px solid var(--line2);color:var(--dim);font-family:ui-monospace,Menlo,Consolas,monospace}
.tag.alerta{color:var(--flag);border-color:#5c4a17;background:#221d0d}
.warn{font-size:13px;color:#e3b341;border-left:2px solid #5c4a17;padding:8px 12px;
  background:#1a1710;border-radius:0 3px 3px 0;margin:14px 0 0}
.note{font-size:13px;color:var(--dim);border-left:2px solid var(--line2);padding-left:12px;margin:0 0 14px}
ul{padding-left:18px;margin:0}
.agenda li{margin-bottom:9px;font-size:14px;list-style:none;margin-left:-18px}
.agenda .d{color:var(--key);font-size:12.5px}
.agenda .c{font-size:10px;letter-spacing:.08em;color:var(--dimmer);border:1px solid var(--line2);
  padding:1px 5px;border-radius:3px;margin-left:6px}
.agenda .clave{color:var(--flag)}
.seg li{margin-bottom:11px}
.est{font-size:10px;letter-spacing:.08em;text-transform:uppercase;padding:1px 6px;border-radius:3px;
  border:1px solid var(--line2);margin-left:6px;font-family:ui-monospace,Menlo,Consolas,monospace}
.e-avanza{color:var(--up);border-color:#2d5136}
.e-estanca{color:var(--flag);border-color:#5c4a17}
.e-revierte{color:var(--down);border-color:#5c2725}
.e-cerrada{color:var(--dim)}
footer{padding:22px 24px;border-top:1px solid var(--line);color:var(--dimmer);
  font-size:11.5px;background:var(--ink2)}
footer a{color:var(--key);text-decoration:none}
.lista a{color:var(--txt);text-decoration:none;display:block;padding:12px 0;border-bottom:1px solid #1e242d}
.lista a:hover{color:var(--key)}
.lista .f{color:var(--dimmer);font-size:12px;font-family:ui-monospace,Menlo,Consolas,monospace}
@media (max-width:640px){
  main{padding:0 14px 30px}header{padding:16px 14px}
  .body{padding-left:16px}.why,.tags{padding-left:0;margin-left:0}
  td.read,th:nth-child(4){display:none}
}
"""

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def e(x):
    return html.escape(str(x or ""))


def fecha_larga(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month]} de {d.year}".upper()


def render_fuentes(fuentes):
    trozos = []
    for f in fuentes or []:
        trozos.append(f'<a href="{e(f.get("url"))}" target="_blank" rel="noopener">{e(f.get("medio"))}</a>')
    return '<span class="sep">·</span>'.join(trozos)


def render_noticia(n, rango):
    flags = n.get("flags") or []
    tags = "".join(f'<span class="tag">{e(c)}</span>' for c in (n.get("categorias") or []))
    if "en_desarrollo" in flags:
        tags += '<span class="tag alerta">En desarrollo</span>'
    if "fuente_unica" in flags:
        tags += '<span class="tag alerta">Fuente unica</span>'

    campos = ""
    for etiqueta, clave in (("Que paso", "que_paso"), ("Contexto", "contexto"),
                            ("Que mirar", "que_mirar")):
        if n.get(clave):
            campos += (f'<div class="fld"><span class="lbl">{etiqueta}</span>'
                       f'<p>{e(n[clave])}</p></div>')

    return f"""<details>
<summary>
  <div class="ttl"><span class="rank">{e(rango)}</span><span>{e(n.get("titulo"))}</span></div>
  <div class="why"><b>Por que importa:</b> {e(n.get("por_que_importa"))}</div>
  <div class="tags">{tags}</div>
</summary>
<div class="body">{campos}
  <div class="fld src"><span class="lbl">Fuentes</span>{render_fuentes(n.get("fuentes"))}</div>
</div>
</details>"""


def render_brief(d, modo, anteriores):
    semanal = modo == "semanal"
    etiqueta = "RESUMEN DE LA SEMANA" if semanal else "BRIEF DIARIO"

    nav = ['<a href="#f5">5YO</a>', '<a href="#ind">Indicadores</a>']
    secciones = []

    # 5YO
    secciones.append(f"""<section id="f5"><h2>Resumen 5YO</h2>
<div class="fiveyo">{e(d.get("resumen_5yo"))}</div></section>""")

    # Indicadores
    filas = ""
    for i in d.get("indicadores", []):
        dirc = {"up": "up", "down": "down", "flat": "flat"}.get(i.get("dir"), "na")
        filas += (f'<tr><td>{e(i.get("nombre"))}</td><td class="v">{e(i.get("valor"))}</td>'
                  f'<td class="v {dirc}">{e(i.get("var"))}</td>'
                  f'<td class="read">{e(i.get("lectura"))}</td></tr>')
    avisos = "".join(f'<div class="warn">{e(a)}</div>' for a in d.get("advertencias") or [])
    sub = "variacion semanal" if semanal else "cierre y operacion intradia"
    secciones.append(f"""<section id="ind"><h2>Indicadores <span>— {sub}</span></h2>
<table><thead><tr><th>Indicador</th><th>Valor</th><th>Var.</th><th>Lectura</th></tr></thead>
<tbody>{filas}</tbody></table>{avisos}</section>""")

    # Bloques
    for b in d.get("bloques", []):
        bid = e(b.get("id"))
        nav.append(f'<a href="#{bid}">{e(b.get("titulo"))}</a>')
        nota = f'<p class="note">{e(b["nota"])}</p>' if b.get("nota") else ""
        prefijo = (b.get("titulo") or "X")[0].upper()
        cuerpo = "".join(render_noticia(n, f"{prefijo}{k}")
                         for k, n in enumerate(b.get("noticias", []), 1))
        secciones.append(f'<section id="{bid}"><h2>{e(b.get("titulo"))} '
                         f'<span>— {len(b.get("noticias", []))} entradas</span></h2>'
                         f'{nota}{cuerpo}</section>')

    # Interes comun
    if d.get("interes_comun"):
        nav.append('<a href="#ic">Interes comun</a>')
        secciones.append('<section id="ic"><h2>Interes comun</h2>'
                         + render_noticia(d["interes_comun"], "★") + "</section>")

    # Seguimiento
    seg = d.get("seguimiento") or {}
    nav.append('<a href="#seg">Seguimiento</a>')
    items = ""
    for it in seg.get("items", []):
        est = (it.get("estado") or "").lower()
        clase = ("e-avanza" if "avanza" in est else "e-estanca" if "estanca" in est
                 else "e-revierte" if "revierte" in est else "e-cerrada")
        link = (f' — <a href="{e(it.get("url"))}" target="_blank" rel="noopener" '
                f'style="color:var(--key);text-decoration:none">ver</a>') if it.get("url") else ""
        items += (f'<li><b>{e(it.get("titulo"))}</b>'
                  f'<span class="est {clase}">{e(it.get("estado"))}</span><br>'
                  f'{e(it.get("cambio"))}{link}</li>')
    abiertas = "".join(f"<li>{e(a)}</li>" for a in seg.get("abiertas") or [])
    bloque_ab = f'<p class="note" style="margin-top:16px">Siguen abiertas:</p><ul>{abiertas}</ul>' if abiertas else ""
    nota_seg = f'<p class="note">{e(seg["nota"])}</p>' if seg.get("nota") else ""
    secciones.append(f'<section id="seg"><h2>Seguimiento</h2>{nota_seg}'
                     f'<ul class="seg">{items}</ul>{bloque_ab}</section>')

    # Agenda
    nav.append('<a href="#ag">Agenda</a>')
    ag = ""
    for a in d.get("agenda", []):
        clave = " clave" if a.get("clave") else ""
        ag += (f'<li><span class="d{clave}">{e(a.get("fecha"))}</span>'
               f'<span class="c">{e(a.get("pais"))}</span> — {e(a.get("texto"))}</li>')
    titulo_ag = "Agenda de la semana entrante" if semanal else "Agenda"
    secciones.append(f'<section id="ag"><h2>{titulo_ag}</h2><ul class="agenda">{ag}</ul></section>')

    total = sum(len(b.get("noticias", [])) for b in d.get("bloques", []))
    enlaces = sum(len(n.get("fuentes") or [])
                  for b in d.get("bloques", []) for n in b.get("noticias", []))

    nav_prev = ""
    if anteriores:
        nav_prev = f' &nbsp;·&nbsp; <a href="archivo/{anteriores[0]}.html">Brief anterior ({anteriores[0]})</a>'

    return f"""<!DOCTYPE html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brief {e(d.get("fecha"))} — Global / Chile / Argentina</title>
<style>{CSS}</style>
</head><body><div class="page">
<header>
  <div class="pill">{etiqueta}</div>
  <h1>Brief — Global · Chile · Argentina</h1>
  <div class="meta">{fecha_larga(d["fecha"])} &nbsp;·&nbsp; CORTE <b>{e(d.get("corte"))}</b><br>
  COBERTURA: <b>{e(d.get("cobertura"))}</b></div>
</header>
<nav>{"".join(nav)}</nav>
<main>{"".join(secciones)}</main>
<footer>
{total} NOTICIAS · {enlaces} ENLACES · VERIFICADO EN 2+ MEDIOS SALVO DONDE SE INDICA · NINGUNA CIFRA ESTIMADA<br>
<a href="archivo/">Ver archivo completo</a>{nav_prev}
</footer>
</div></body></html>"""


def render_indice(entradas):
    filas = ""
    for iso, tipo in entradas:
        et = "Semanal" if tipo == "semanal" else "Diario"
        filas += (f'<a href="{iso}.html"><span class="f">{iso} · {et}</span><br>'
                  f'Brief del {fecha_larga(iso).lower()}</a>')
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Archivo de briefs</title><style>{CSS}</style></head>
<body><div class="page">
<header><h1>Archivo de briefs</h1>
<div class="meta">{len(entradas)} EDICIONES GUARDADAS</div></header>
<main><section><h2>Todas las ediciones</h2><div class="lista">{filas}</div></section></main>
<footer><a href="../">Volver al brief mas reciente</a></footer>
</div></body></html>"""


# --------------------------------------------------------------------------

def main():
    os.makedirs(ARCHIVO, exist_ok=True)
    hoy = datetime.datetime.now(TZ)

    if len(sys.argv) > 1 and sys.argv[1] in ("diario", "semanal"):
        modo = sys.argv[1]
    else:
        modo = "semanal" if hoy.weekday() == 6 else "diario"
    print(f"Modo: {modo}")

    previos = []
    for ruta in sorted(glob.glob(os.path.join(ARCHIVO, "*.json"))):
        try:
            with open(ruta, encoding="utf-8") as f:
                previos.append(json.load(f))
        except Exception:
            pass

    corte_anterior = None
    if previos:
        ult = previos[-1]
        corte_anterior = f'{ult.get("fecha")} {ult.get("corte", "")}'.strip()

    dias = 7 if modo == "semanal" else 1
    contexto = resumen_para_seguimiento(previos, dias) if previos else ""

    print("Generando... esto tarda entre 2 y 5 minutos.")
    datos = pedir_brief(modo, corte_anterior, contexto)
    datos["tipo"] = modo
    if not datos.get("fecha"):
        datos["fecha"] = hoy.strftime("%Y-%m-%d")

    iso = datos["fecha"]
    with open(os.path.join(ARCHIVO, f"{iso}.json"), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)

    anteriores = sorted(
        os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ARCHIVO, "*.json"))
        if os.path.basename(p)[:-5] != iso
    )[::-1]

    pagina = render_brief(datos, modo, anteriores)
    with open(os.path.join(ARCHIVO, f"{iso}.html"), "w", encoding="utf-8") as f:
        f.write(pagina.replace('href="archivo/', 'href="'))
    with open(os.path.join(RAIZ, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina)

    entradas = []
    for ruta in sorted(glob.glob(os.path.join(ARCHIVO, "*.json")), reverse=True):
        with open(ruta, encoding="utf-8") as f:
            j = json.load(f)
        entradas.append((os.path.basename(ruta)[:-5], j.get("tipo", "diario")))
    with open(os.path.join(ARCHIVO, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_indice(entradas))

    total = sum(len(b.get("noticias", [])) for b in datos.get("bloques", []))
    print(f"Listo: {iso} ({modo}), {total} noticias, {len(entradas)} ediciones en archivo.")


if __name__ == "__main__":
    main()
