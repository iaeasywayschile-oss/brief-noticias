#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arma una portada de titulares leyendo los RSS de varios medios.
No usa IA, no necesita clave de API y no cuesta nada.

Uso:  python agregador.py
Lee la lista de medios de feeds.txt y escribe titulares.html
"""

import os
import re
import html
import hashlib
import datetime
import zoneinfo
import urllib.request
import xml.etree.ElementTree as ET

TZ = zoneinfo.ZoneInfo("America/Santiago")
RAIZ = os.path.dirname(os.path.abspath(__file__))
HORAS = 24          # cuantas horas hacia atras mostrar
POR_BLOQUE = 18     # maximo de titulares por bloque
AGENTE = "Mozilla/5.0 (compatible; portada-titulares/1.0)"

ORDEN = ["Global", "Chile", "Argentina"]


def leer_feeds():
    """feeds.txt: una linea por medio -> Bloque | Nombre | URL"""
    feeds = []
    with open(os.path.join(RAIZ, "feeds.txt"), encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            partes = [p.strip() for p in linea.split("|")]
            if len(partes) == 3:
                feeds.append(tuple(partes))
    return feeds


def limpiar(texto):
    texto = re.sub(r"<[^>]+>", "", texto or "")
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def parsear_fecha(txt):
    if not txt:
        return None
    txt = txt.strip()
    formatos = ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"]
    for fmt in formatos:
        try:
            d = datetime.datetime.strptime(txt.replace("GMT", "+0000"), fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return d.astimezone(TZ)
        except ValueError:
            continue
    return None


def bajar(url):
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(pedido, timeout=25) as r:
        return r.read()


def extraer(xml_bytes, medio, bloque):
    raiz = ET.fromstring(xml_bytes)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = raiz.findall(".//item") or raiz.findall(".//atom:entry", ns)
    salida = []
    for it in items:
        def campo(*nombres):
            for n in nombres:
                el = it.find(n) if not n.startswith("atom:") else it.find(n, ns)
                if el is not None:
                    if el.text and el.text.strip():
                        return el.text
                    if el.get("href"):
                        return el.get("href")
            return ""

        titulo = limpiar(campo("title", "atom:title"))
        enlace = limpiar(campo("link", "atom:link"))
        bajada = limpiar(campo("description", "atom:summary"))[:220]
        fecha = parsear_fecha(campo("pubDate", "atom:updated", "atom:published"))
        if not titulo or not enlace:
            continue
        salida.append({
            "titulo": titulo, "enlace": enlace, "bajada": bajada,
            "fecha": fecha, "medio": medio, "bloque": bloque,
            "clave": hashlib.md5(re.sub(r"[^a-z0-9]", "", titulo.lower()[:70])
                                 .encode()).hexdigest(),
        })
    return salida


def hace_cuanto(d, ahora):
    if not d:
        return ""
    m = int((ahora - d).total_seconds() // 60)
    if m < 1:
        return "recien"
    if m < 60:
        return f"hace {m} min"
    h = m // 60
    if h < 24:
        return f"hace {h} h"
    return f"hace {h // 24} d"


CSS = """
:root{--ink:#0d1117;--ink2:#161b22;--line:#2a323d;--line2:#39424f;
  --txt:#dfe4ec;--dim:#8b95a5;--dimmer:#5e6875;--key:#58a6ff;--flag:#d29922}
*{box-sizing:border-box}
body{background:var(--ink);color:var(--txt);margin:0;font-size:15px;line-height:1.6;
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.page{max-width:1100px;margin:0 auto;border-left:1px solid var(--line);
  border-right:1px solid var(--line);min-height:100vh}
header{padding:22px 24px;border-bottom:1px solid var(--line);background:var(--ink2)}
h1{font-size:19px;margin:0 0 6px;font-weight:650}
.meta{font-size:12px;color:var(--dim);letter-spacing:.02em;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0}
.col{border-right:1px solid var(--line);padding:0 18px 30px}
.col:last-child{border-right:none}
h2{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);
  font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line);
  font-family:ui-monospace,Menlo,Consolas,monospace}
h2 span{color:var(--dimmer);letter-spacing:.02em;text-transform:none;font-weight:400}
article{padding:12px 0;border-bottom:1px solid #1e242d}
article a{color:var(--txt);text-decoration:none;font-size:14.5px;font-weight:500;line-height:1.4}
article a:hover{color:var(--key)}
.bajada{font-size:12.5px;color:var(--dim);line-height:1.45;margin:5px 0 0}
.fuente{font-size:11px;color:var(--dimmer);margin-top:6px;
  font-family:ui-monospace,Menlo,Consolas,monospace;letter-spacing:.03em}
.fuente b{color:var(--dim);font-weight:400}
.aviso{margin:18px 24px 0;font-size:12.5px;color:var(--flag);border-left:2px solid #5c4a17;
  background:#1a1710;padding:9px 12px}
footer{padding:20px 24px;border-top:1px solid var(--line);color:var(--dimmer);font-size:11.5px;
  background:var(--ink2);font-family:ui-monospace,Menlo,Consolas,monospace}
footer a{color:var(--key);text-decoration:none}
@media (max-width:820px){
  .cols{grid-template-columns:1fr}
  .col{border-right:none;border-bottom:1px solid var(--line)}
}
"""


def render(grupos, fallidos, ahora):
    columnas = ""
    for bloque in ORDEN:
        notas = grupos.get(bloque, [])
        arts = ""
        for n in notas:
            bajada = f'<p class="bajada">{html.escape(n["bajada"])}</p>' if n["bajada"] else ""
            arts += (f'<article><a href="{html.escape(n["enlace"])}" target="_blank" '
                     f'rel="noopener">{html.escape(n["titulo"])}</a>{bajada}'
                     f'<div class="fuente"><b>{html.escape(n["medio"])}</b> · '
                     f'{hace_cuanto(n["fecha"], ahora)}</div></article>')
        if not arts:
            arts = '<p class="bajada">Sin titulares nuevos en las ultimas horas.</p>'
        columnas += (f'<div class="col"><h2>{bloque} <span>— {len(notas)}</span></h2>'
                     f'{arts}</div>')

    aviso = ""
    if fallidos:
        lista = ", ".join(html.escape(m) for m in fallidos)
        aviso = (f'<div class="aviso">No respondieron: {lista}. '
                 f'Suele ser que el medio cambio la direccion de su RSS. '
                 f'Corregila en feeds.txt.</div>')

    total = sum(len(v) for v in grupos.values())
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="1800">
<title>Titulares — Global / Chile / Argentina</title>
<style>{CSS}</style></head>
<body><div class="page">
<header><h1>Titulares — Global · Chile · Argentina</h1>
<div class="meta">ACTUALIZADO {ahora.strftime('%d/%m/%Y %H:%M')} HORA DE CHILE ·
ULTIMAS {HORAS} HORAS · {total} TITULARES</div></header>
{aviso}
<div class="cols">{columnas}</div>
<footer>Titulares tomados directo del RSS de cada medio. Sin verificacion ni edicion:
el orden es por hora de publicacion, no por importancia. La pagina se refresca sola
cada 30 minutos y se regenera cada hora.</footer>
</div></body></html>"""


def main():
    ahora = datetime.datetime.now(TZ)
    corte = ahora - datetime.timedelta(hours=HORAS)
    notas, fallidos, vistos = [], [], set()

    for bloque, medio, url in leer_feeds():
        try:
            for n in extraer(bajar(url), medio, bloque):
                if n["clave"] in vistos:
                    continue
                if n["fecha"] and n["fecha"] < corte:
                    continue
                vistos.add(n["clave"])
                notas.append(n)
            print(f"ok   {medio}")
        except Exception as err:
            fallidos.append(medio)
            print(f"FALLA {medio}: {err}")

    grupos = {}
    for b in ORDEN:
        del_bloque = [n for n in notas if n["bloque"] == b]
        del_bloque.sort(key=lambda n: n["fecha"] or corte, reverse=True)
        grupos[b] = del_bloque[:POR_BLOQUE]

    with open(os.path.join(RAIZ, "titulares.html"), "w", encoding="utf-8") as f:
        f.write(render(grupos, fallidos, ahora))

    print(f"Listo: {sum(len(v) for v in grupos.values())} titulares, "
          f"{len(fallidos)} medios sin responder.")


if __name__ == "__main__":
    main()
