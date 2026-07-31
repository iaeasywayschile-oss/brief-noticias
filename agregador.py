#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arma una portada de titulares leyendo los RSS de varios medios.
No usa IA, no necesita clave de API y no cuesta nada.

Cada titular se clasifica en una categoria (Economia, Politica, Sociedad,
Tecnologia, Deporte o General) usando primero la seccion que trae el RSS
y, si no viene, adivinando por palabras del titulo. Es una aproximacion
automatica: acierta la mayoria, pero algunos caen en General.

Uso:  python agregador.py
Lee la lista de medios de feeds.txt y escribe titulares.html
"""

import os
import re
import html
import hashlib
import datetime
import zoneinfo
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

TZ = zoneinfo.ZoneInfo("America/Santiago")
RAIZ = os.path.dirname(os.path.abspath(__file__))
HORAS = 24
POR_BLOQUE = 20
AGENTE = "Mozilla/5.0 (compatible; portada-titulares/1.0)"

ORDEN = ["Global", "Chile", "Argentina", "China / Importacion"]

# Palabras que marcan una noticia como relevante para importar de China.
# Un titular de CUALQUIER medio que mencione alguna de estas se copia
# tambien a la columna China / Importacion. Es un filtro por tema, no por medio.
PISTAS_CHINA = [
    # fletes y logistica
    "flete", "contenedor", "naviera", "maersk", "puerto de", "carga maritima",
    "transporte maritimo", "buque", "shanghai", "shenzhen", "cantón", "canton",
    "ningbo", "ruta maritima", "cadena de suministro", "cadena de abastecimiento",
    "logistica", "estrecho de ormuz", "canal de suez", "panama",
    # comercio y aduana
    "arancel", "aduana", "importacion", "importa", "exportacion china",
    "comercio con china", "guerra comercial", "aduanero", "sobretasa",
    "antidumping", "salvaguardia", "tratado de libre comercio", "tlc",
    # china macro
    "china", "yuan", "pekin", "beijing", "manufactura china", "fabrica china",
    "pmi de china", "economia china", "banco popular de china", "xi jinping",
    "aliexpress", "alibaba", "temu", "shein",
    # productos / electro
    "electrodomestico", "linea blanca", "importadores",
]

CATEGORIAS = ["Economia", "Politica", "Sociedad", "Tecnologia", "Deporte", "General"]
COLOR_CAT = {
    "Economia":   ("#e3b341", "#5c4a17", "#221d0d"),
    "Politica":   ("#d2a8ff", "#4c3a63", "#1c1626"),
    "Sociedad":   ("#7ee787", "#2d5136", "#101d15"),
    "Tecnologia": ("#79c0ff", "#1f4266", "#0d1a26"),
    "Deporte":    ("#f0997b", "#5c3a2b", "#241511"),
    "General":    ("#8b95a5", "#39424f", "#1a1f27"),
}

PISTAS = {
    "Economia": ["dolar", "peso", "inflacion", "precio", "banco central", "bolsa",
                 "merval", "ipsa", "cobre", "riesgo pais", "fmi", "deuda", "tasa",
                 "impuesto", "arancel", "exporta", "importa", "pib", "empleo",
                 "salario", "mercado", "inversion", "acciones", "bono", "cepo",
                 "reforma tributaria", "economia", "fiscal", "subsidio", "tarifa",
                 "credito", "jubilacion", "pyme", "empresa"],
    "Politica": ["presidente", "gobierno", "congreso", "senado", "diputado",
                 "ministro", "eleccion", "campana", "partido", "kast", "milei",
                 "boric", "oposicion", "veto", "proyecto de ley", "constitucion",
                 "canciller", "parlamento", "votacion", "kicillof", "trump",
                 "putin", "cumbre", "acuerdo", "cancilleria"],
    "Sociedad": ["muerto", "herido", "accidente", "temporal", "lluvia", "sismo",
                 "terremoto", "incendio", "policia", "crimen", "femicidio",
                 "salud", "hospital", "educacion", "protesta", "marcha", "delito",
                 "narco", "emergencia", "rescate", "victima", "colegio", "robo",
                 "detenido", "fallecio"],
    "Tecnologia": ["inteligencia artificial", " ia ", "tecnologia", " app ",
                   "software", "google", "apple", "microsoft", "openai", "chip",
                   "startup", "ciberataque", "hacker", "robot", "satelite",
                   "nasa", "cientific", "descubr", "espacial", "telescopio",
                   "algoritmo"],
    "Deporte": ["gol", "futbol", "mundial", "seleccion", "campeon", "liga",
                "torneo", "tenis", "messi", "colo colo", "river", "boca",
                "fifa", "clasico", "copa", "jugador", " dt ", "estadio",
                "eliminatorias"],
}


def fold(t):
    """minusculas, sin tildes; para comparar texto."""
    t = (t or "").lower()
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


def es_china(titulo, bajada):
    """True si el titular menciona algo relevante para importar de China."""
    t = " " + fold(titulo + " " + (bajada or "")) + " "
    return any(p in t for p in PISTAS_CHINA)


def leer_feeds():
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


def clasificar(titulo, seccion):
    sec = fold(seccion)
    mapa = {
        "econom": "Economia", "negocio": "Economia", "finanz": "Economia",
        "mercado": "Economia", "dinero": "Economia",
        "politic": "Politica", "eleccion": "Politica", "gobierno": "Politica",
        "mundo": "Politica", "internacional": "Politica",
        "sociedad": "Sociedad", "nacional": "Sociedad", "policial": "Sociedad",
        "sucesos": "Sociedad", "salud": "Sociedad", "educacion": "Sociedad",
        "tecnolog": "Tecnologia", "ciencia": "Tecnologia", "innovacion": "Tecnologia",
        "deporte": "Deporte", "futbol": "Deporte",
    }
    for clave, cat in mapa.items():
        if clave in sec:
            return cat

    t = " " + fold(titulo) + " "
    puntajes = {cat: sum(1 for p in pistas if p in t) for cat, pistas in PISTAS.items()}
    mejor = max(puntajes, key=puntajes.get)
    return mejor if puntajes[mejor] > 0 else "General"


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

        seccion = ""
        cat_el = it.find("category")
        if cat_el is not None:
            seccion = cat_el.get("term") or cat_el.text or ""

        if not titulo or not enlace:
            continue
        salida.append({
            "titulo": titulo, "enlace": enlace, "bajada": bajada,
            "fecha": fecha, "medio": medio, "bloque": bloque,
            "categoria": clasificar(titulo, seccion),
            "clave": hashlib.md5(re.sub(r"[^a-z0-9]", "", titulo.lower()[:70]).encode()).hexdigest(),
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


def css():
    base = """:root{--ink:#0d1117;--ink2:#161b22;--line:#2a323d;--line2:#39424f;
  --txt:#dfe4ec;--dim:#8b95a5;--dimmer:#5e6875;--key:#58a6ff;--flag:#d29922}
*{box-sizing:border-box}
body{background:var(--ink);color:var(--txt);margin:0;font-size:15px;line-height:1.6;
  font-family:ui-sans-serif,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.page{max-width:1100px;margin:0 auto;border-left:1px solid var(--line);
  border-right:1px solid var(--line);min-height:100vh}
header{padding:22px 24px 16px;border-bottom:1px solid var(--line);background:var(--ink2)}
h1{font-size:19px;margin:0 0 6px;font-weight:650}
.meta{font-size:12px;color:var(--dim);letter-spacing:.02em;
  font-family:ui-monospace,Menlo,Consolas,monospace}
.filtros{display:flex;gap:6px;flex-wrap:wrap;padding:14px 24px;border-bottom:1px solid var(--line);background:var(--ink2)}
.filtro{font-size:11px;letter-spacing:.05em;text-transform:uppercase;padding:4px 11px;
  border-radius:20px;border:1px solid var(--line2);color:var(--dim);cursor:pointer;
  background:transparent;font-family:ui-monospace,Menlo,Consolas,monospace}
.filtro:hover{color:var(--txt);border-color:var(--dim)}
.filtro.on{background:var(--txt);color:var(--ink);border-color:var(--txt);font-weight:600}
.cols{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0}
.col-china{background:#0f1620}
.col{border-right:1px solid var(--line);padding:0 18px 30px}
.col:last-child{border-right:none}
h2{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);
  font-weight:600;margin:26px 0 12px;padding-bottom:8px;border-bottom:1px solid var(--line);
  font-family:ui-monospace,Menlo,Consolas,monospace}
h2 span{color:var(--dimmer);letter-spacing:.02em;text-transform:none;font-weight:400}
article{padding:12px 0;border-bottom:1px solid #1e242d}
.tag{display:inline-block;font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;
  padding:2px 7px;border-radius:3px;border:1px solid;margin-bottom:6px;
  font-family:ui-monospace,Menlo,Consolas,monospace}
article a.tit{color:var(--txt);text-decoration:none;font-size:14.5px;font-weight:500;
  line-height:1.4;display:block}
article a.tit:hover{color:var(--key)}
.bajada{font-size:12.5px;color:var(--dim);line-height:1.45;margin:5px 0 0}
.fuente{font-size:11px;color:var(--dimmer);margin-top:6px;
  font-family:ui-monospace,Menlo,Consolas,monospace;letter-spacing:.03em}
.fuente b{color:var(--dim);font-weight:400}
.aviso{margin:14px 24px 0;font-size:12.5px;color:var(--flag);border-left:2px solid #5c4a17;
  background:#1a1710;padding:9px 12px}
.vacio{font-size:12.5px;color:var(--dimmer);padding:10px 0}
footer{padding:20px 24px;border-top:1px solid var(--line);color:var(--dimmer);font-size:11.5px;
  background:var(--ink2);font-family:ui-monospace,Menlo,Consolas,monospace}
@media (max-width:1000px){.cols{grid-template-columns:repeat(2,1fr)}}
@media (max-width:640px){.cols{grid-template-columns:1fr}
  .col{border-right:none;border-bottom:1px solid var(--line)}}"""
    extra = "\n".join(f'.t-{c.lower()}{{color:{fg};border-color:{bd};background:{bg}}}'
                      for c, (fg, bd, bg) in COLOR_CAT.items())
    return base + "\n" + extra


def render(grupos, fallidos, ahora):
    botones = ['<button class="filtro on" data-cat="todas" onclick="filtrar(this)">Todas</button>']
    for cat in CATEGORIAS:
        botones.append(f'<button class="filtro" data-cat="{cat.lower()}" onclick="filtrar(this)">{cat}</button>')

    columnas = ""
    for bloque in ORDEN:
        es_col_china = bloque == "China / Importacion"
        notas = grupos.get(bloque, [])
        arts = ""
        for n in notas:
            c = n["categoria"]
            bajada = f'<p class="bajada">{html.escape(n["bajada"])}</p>' if n["bajada"] else ""
            # En la columna China, mostrar de que pais salio el titular.
            origen = ""
            if es_col_china and n["bloque"] != "China / Importacion":
                origen = f' &middot; {html.escape(n["bloque"])}'
            arts += (f'<article data-cat="{c.lower()}">'
                     f'<span class="tag t-{c.lower()}">{c}</span>'
                     f'<a class="tit" href="{html.escape(n["enlace"])}" target="_blank" rel="noopener">{html.escape(n["titulo"])}</a>'
                     f'{bajada}<div class="fuente"><b>{html.escape(n["medio"])}</b>{origen} &middot; {hace_cuanto(n["fecha"], ahora)}</div></article>')
        if not arts:
            arts = '<p class="vacio">Sin titulares del tema hoy.</p>' if es_col_china else '<p class="vacio">Sin titulares nuevos.</p>'
        clase_col = "col col-china" if es_col_china else "col"
        columnas += (f'<div class="{clase_col}"><h2>{bloque} <span>&mdash; {len(notas)}</span></h2>'
                     f'<div class="lista">{arts}</div>'
                     f'<p class="vacio" data-empty hidden>Nada en esta categoria.</p></div>')

    aviso = ""
    if fallidos:
        lista = ", ".join(html.escape(m) for m in fallidos)
        aviso = (f'<div class="aviso">No respondieron: {lista}. '
                 f'Suele ser que el medio cambio la direccion de su RSS. Corregila en feeds.txt.</div>')

    total = sum(len(v) for v in grupos.values())
    script = ("function filtrar(btn){"
              "document.querySelectorAll('.filtro').forEach(function(b){b.classList.remove('on')});"
              "btn.classList.add('on');var cat=btn.dataset.cat;"
              "document.querySelectorAll('.col').forEach(function(col){var vis=0;"
              "col.querySelectorAll('article').forEach(function(a){"
              "var ok=(cat==='todas'||a.dataset.cat===cat);a.hidden=!ok;if(ok)vis++;});"
              "var e=col.querySelector('[data-empty]');if(e)e.hidden=(vis>0);});}")

    return ("<!DOCTYPE html>\n<html lang=\"es\"><head><meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
            "<meta http-equiv=\"refresh\" content=\"1800\">\n"
            "<title>Titulares &mdash; Global / Chile / Argentina</title>\n"
            f"<style>{css()}</style></head>\n<body><div class=\"page\">\n"
            "<header><h1>Titulares &mdash; Global &middot; Chile &middot; Argentina</h1>\n"
            f"<div class=\"meta\">ACTUALIZADO {ahora.strftime('%d/%m/%Y %H:%M')} HORA DE CHILE &middot; "
            f"ULTIMAS {HORAS} HORAS &middot; {total} TITULARES</div></header>\n"
            f"<div class=\"filtros\">{''.join(botones)}</div>\n{aviso}\n"
            f"<div class=\"cols\">{columnas}</div>\n"
            "<footer>Titulares tomados directo del RSS de cada medio. La categoria se deduce "
            "automaticamente y a veces cae en General. Sin verificacion ni edicion: el orden es "
            "por hora, no por importancia. Se refresca sola cada 30 minutos.</footer>\n"
            f"</div>\n<script>{script}</script>\n</body></html>")


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
    # Columnas geograficas: cada titular en su bloque de origen.
    for b in ["Global", "Chile", "Argentina"]:
        db = [n for n in notas if n["bloque"] == b]
        db.sort(key=lambda n: n["fecha"] or corte, reverse=True)
        grupos[b] = db[:POR_BLOQUE]

    # Columna China / Importacion: titulares de CUALQUIER bloque que hablen
    # del tema. Se muestra de que pais venia con una marca al lado.
    china = [n for n in notas if es_china(n["titulo"], n["bajada"])]
    china.sort(key=lambda n: n["fecha"] or corte, reverse=True)
    grupos["China / Importacion"] = china[:POR_BLOQUE]

    with open(os.path.join(RAIZ, "titulares.html"), "w", encoding="utf-8") as f:
        f.write(render(grupos, fallidos, ahora))

    print(f"Listo: {sum(len(v) for v in grupos.values())} titulares, {len(fallidos)} sin responder.")


if __name__ == "__main__":
    main()
