#!/usr/bin/env python3
"""Perfil personal interconectado a partir de tus chats y proyectos de Claude.

Pasos (todos corren con `claude -p`, sin API key aparte):
  ingest    export de claude.ai  -> salida/fuentes/<dominio>/*.md
  analizar  cada dominio         -> salida/dominios/<dominio>.json (necesidades, patrones, metas...)
  conectar  todos los dominios   -> salida/grafo.json + grafo.md (red interconectada)
  perfil    red completa         -> salida/PERFIL.md (necesidades y como preservarlas)
  contexto  pregunta             -> bloque de contexto elegido (manual o automatico)
  preguntar pregunta             -> contexto + pregunta enviada a Claude
  instalar                       -> skill /mi-perfil en ~/.claude/skills
  todo      ingest+analizar+conectar+perfil
"""
import argparse, json, os, re, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get("PERFIL_OUT", ROOT / "salida"))
MODEL = os.environ.get("PERFIL_MODEL", "sonnet")
CHUNK = 60_000  # caracteres por llamada


# ---------- utilidades ----------
def slug(s):
    s = re.sub(r"[^\w\-]+", "-", s.lower(), flags=re.UNICODE).strip("-")
    return s[:60] or "sin-titulo"


def claude(prompt, model=None):
    r = subprocess.run(["claude", "-p", "--model", model or MODEL],
                       input=prompt, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"claude fallo: {r.stderr.strip()[:500]}")
    return r.stdout.strip()


def claude_json(prompt):
    for _ in range(2):
        out = claude(prompt)
        m = re.search(r"\{.*\}", out, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        prompt += "\n\nIMPORTANTE: responde SOLO con JSON valido, sin texto extra."
    sys.exit("No se obtuvo JSON valido de Claude.")


def load_json(p, default=None):
    return json.loads(Path(p).read_text()) if Path(p).exists() else default


def dump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2))


def msg_text(m):
    if m.get("text"):
        return m["text"]
    return "\n".join(c.get("text", "") for c in m.get("content", []) if c.get("type") == "text")


# ---------- 1. ingest ----------
def read_export(path):
    p = Path(path)
    if p.suffix == ".zip":
        z = zipfile.ZipFile(p)
        get = lambda n: json.loads(z.read(n)) if n in z.namelist() else []
    else:
        get = lambda n: load_json(p / n, [])
    return get("conversations.json"), get("projects.json")


def cmd_ingest(a):
    convs, projects = read_export(a.export)
    pname = {p["uuid"]: p.get("name", "proyecto") for p in projects}
    src = OUT / "fuentes"
    n = 0
    for p in projects:  # instrucciones y documentos del proyecto = contexto declarado
        d = src / slug(p.get("name", "proyecto"))
        d.mkdir(parents=True, exist_ok=True)
        body = f"# Proyecto: {p.get('name')}\n\n{p.get('description') or ''}\n\n{p.get('prompt_template') or ''}\n"
        for doc in p.get("docs", []):
            body += f"\n## Documento: {doc.get('filename')}\n{(doc.get('content') or '')[:20000]}\n"
        (d / "00_proyecto.md").write_text(body)
    for c in convs:
        dom = slug(pname.get(c.get("project_uuid"), "sin-proyecto"))
        d = src / dom
        d.mkdir(parents=True, exist_ok=True)
        lines = [f"# {c.get('name') or 'Sin titulo'}", f"fecha: {c.get('created_at', '')[:10]}\n"]
        for m in c.get("chat_messages", []):
            t = msg_text(m).strip()
            if not t:
                continue
            if m.get("sender") == "human":
                lines.append(f"**YO:** {t}\n")
            else:  # lo que dice Claude se recorta: lo valioso es lo que dice el usuario
                lines.append(f"*Claude:* {t[:a.recorte]}{'...' if len(t) > a.recorte else ''}\n")
        (d / f"{c.get('created_at', '')[:10]}_{slug(c.get('name') or '')}.md").write_text("\n".join(lines))
        n += 1
    for extra in a.extra or []:  # carpetas con notas propias: carpeta = dominio
        e = Path(extra)
        d = src / slug(e.name)
        d.mkdir(parents=True, exist_ok=True)
        for f in list(e.rglob("*.md")) + list(e.rglob("*.txt")):
            (d / f.name).write_text(f.read_text(errors="ignore"))
    print(f"{n} conversaciones, {len(projects)} proyectos -> {src}")
    if (src / "sin-proyecto").exists():
        print("Hay chats sin proyecto. Corre `agrupar` para asignarles un dominio tematico.")


def cmd_agrupar(a):
    """Reparte los chats 'sin-proyecto' en dominios tematicos usando solo los titulos."""
    src = OUT / "fuentes"
    d = src / "sin-proyecto"
    files = sorted(d.glob("*.md"))
    if not files:
        return print("Nada que agrupar.")
    titles = {f.name: f.read_text().splitlines()[0][2:] for f in files}
    existing = [p.name for p in src.iterdir() if p.is_dir() and p.name != "sin-proyecto"]
    mapping = {}
    items = list(titles.items())
    for i in range(0, len(items), 150):
        batch = dict(items[i:i + 150])
        r = claude_json(
            "Asigna cada conversacion a un dominio de vida (ej: musica, trabajo, salud, orden-planificacion, "
            f"finanzas, relaciones, aprendizaje). Reutiliza estos dominios si encajan: {existing}. "
            "Maximo 10 dominios en total, nombres cortos en minusculas sin espacios.\n"
            'Responde SOLO JSON: {"archivo.md": "dominio", ...}\n\n' + json.dumps(batch, ensure_ascii=False))
        mapping.update(r)
        existing = sorted(set(existing) | set(r.values()))
    for f in files:
        dom = slug(mapping.get(f.name, "otros"))
        (src / dom).mkdir(exist_ok=True)
        f.rename(src / dom / f.name)
    print("Dominios:", ", ".join(sorted(set(mapping.values()))))


# ---------- 2. analizar ----------
SCHEMA = """{
 "necesidades": [{"necesidad": "...", "evidencia": ["cita o hecho breve"], "senal_de_carencia": "...", "como_preservarla": "..."}],
 "patrones_conducta": [{"patron": "...", "evidencia": ["..."]}],
 "valores": ["..."], "metas": ["..."], "tensiones": ["conflictos internos o entre areas"],
 "hechos_clave": ["datos estables sobre la persona, su situacion, herramientas, rutinas"],
 "entidades": ["personas, proyectos, obras, herramientas recurrentes"],
 "resumen": "3-5 frases sobre que significa este dominio en la vida de la persona"
}"""


def analyze_prompt(dom, text):
    return (f"Eres un analista cuidadoso de personas. Abajo hay conversaciones de la persona (YO) con Claude, "
            f"del dominio '{dom}'. Extrae lo que revela de sus necesidades humanas (autonomia, descanso, "
            "sentido, conexion, creatividad, seguridad, orden, reconocimiento, etc.), su conducta real "
            "(no lo que dice que quiere, sino lo que hace) y como preservar esas necesidades. "
            "No inventes: cada afirmacion debe tener evidencia. Espanol. Responde SOLO JSON con este esquema:\n"
            f"{SCHEMA}\n\n=== CONVERSACIONES ===\n{text}")


def merge_prompt(dom, parts):
    return (f"Fusiona estos analisis parciales del dominio '{dom}' en uno solo, sin duplicados, conservando "
            f"la evidencia mas fuerte. Mismo esquema, SOLO JSON:\n{SCHEMA}\n\n" + json.dumps(parts, ensure_ascii=False))


def cmd_analizar(a):
    src = OUT / "fuentes"
    for d in sorted(p for p in src.iterdir() if p.is_dir()):
        target = OUT / "dominios" / f"{d.name}.json"
        if target.exists() and not a.rehacer:
            print(f"[{d.name}] ya analizado (usa --rehacer)")
            continue
        docs = [f.read_text() for f in sorted(d.glob("*.md"))]
        chunks, cur = [], ""
        for t in docs:
            if len(cur) + len(t) > CHUNK and cur:
                chunks.append(cur)
                cur = ""
            cur += t[:CHUNK] + "\n\n---\n\n"
        if cur:
            chunks.append(cur)
        print(f"[{d.name}] {len(docs)} docs, {len(chunks)} bloques")
        parts = [claude_json(analyze_prompt(d.name, c)) for c in chunks]
        res = parts[0] if len(parts) == 1 else claude_json(merge_prompt(d.name, parts))
        res["dominio"] = d.name
        dump(target, res)


# ---------- 3. conectar ----------
def compact(dom):
    return {k: dom.get(k) for k in ("dominio", "resumen", "necesidades", "patrones_conducta", "valores",
                                   "metas", "tensiones", "entidades")}


def cmd_conectar(a):
    doms = [load_json(p) for p in sorted((OUT / "dominios").glob("*.json"))]
    if not doms:
        sys.exit("Primero corre `analizar`.")
    g = claude_json(
        "Construye una red interconectada de la persona a partir de estos dominios de su vida. "
        "Nodos: tipo en {dominio, necesidad, patron, valor, meta, tension, entidad}. Une nodos de dominios distintos "
        "que sean la misma necesidad o se afecten (ej: el dominio 'musica' y el de 'orden-planificacion' "
        "comparten la necesidad de estructura para crear). Aristas: relacion en {sirve_a, bloquea, "
        "refuerza, tension_con, es_instancia_de, depende_de} con una frase de explicacion. Prioriza conexiones "
        "NO obvias entre dominios. Responde SOLO JSON:\n"
        '{"nodos": [{"id": "n1", "tipo": "...", "nombre": "...", "dominios": ["..."]}], '
        '"aristas": [{"de": "n1", "a": "n2", "relacion": "...", "porque": "..."}], '
        '"conexiones_clave": ["3-8 hallazgos transversales en una frase"]}\n\n'
        + json.dumps([compact(d) for d in doms], ensure_ascii=False))
    dump(OUT / "grafo.json", g)
    names = {n["id"]: n["nombre"] for n in g["nodos"]}
    md = ["# Red de conexiones\n", "## Hallazgos transversales"] + [f"- {c}" for c in g["conexiones_clave"]]
    md += ["\n## Mapa", "```mermaid", "graph LR"]
    md += [f'  {e["de"]} -- {e["relacion"]} --> {e["a"]}' for e in g["aristas"]]
    md += [f'  {n["id"]}["{n["nombre"]}"]' for n in g["nodos"]] + ["```", "\n## Aristas"]
    md += [f'- **{names.get(e["de"])}** {e["relacion"]} **{names.get(e["a"])}**: {e["porque"]}' for e in g["aristas"]]
    (OUT / "grafo.md").write_text("\n".join(md))
    print(f"{len(g['nodos'])} nodos, {len(g['aristas'])} aristas -> {OUT/'grafo.md'}")


# ---------- 4. perfil ----------
def cmd_perfil(a):
    doms = [load_json(p) for p in sorted((OUT / "dominios").glob("*.json"))]
    g = load_json(OUT / "grafo.json", {})
    txt = claude(
        "Escribe en espanol el PERFIL de esta persona como ser humano, a partir de sus dominios y la red de "
        "conexiones. Estructura: 1) Quien es (sintesis, honesta y respetuosa); 2) Necesidades humanas "
        "principales, ordenadas por importancia: para cada una evidencia, senales de que esta insatisfecha "
        "y COMO PRESERVARLA (acciones concretas, minimas y sostenibles); 3) Patrones de conducta (utiles y "
        "saboteadores); 4) Conexiones entre areas de su vida; 5) Tensiones y riesgos; 6) Como debe Claude "
        "acompanarle (tono, que evitar, cuando ser directo). No inventes: marca como [hipotesis] lo poco evidenciado.\n\n"
        "DOMINIOS:\n" + json.dumps(doms, ensure_ascii=False) + "\n\nRED:\n" + json.dumps(g, ensure_ascii=False))
    (OUT / "PERFIL.md").write_text(txt)
    print(f"-> {OUT/'PERFIL.md'}")


# ---------- 5. contexto selectivo ----------
def domains():
    return {p.stem: load_json(p) for p in sorted((OUT / "dominios").glob("*.json"))}


def build_context(question, chosen):
    doms = domains()
    chosen = [c for c in chosen if c in doms]
    parts = []
    perfil = OUT / "PERFIL.md"
    if perfil.exists():
        parts.append("## Perfil base\n" + perfil.read_text()[:6000])
    g = load_json(OUT / "grafo.json", {})
    for c in chosen:
        parts.append(f"## Dominio: {c}\n" + json.dumps(doms[c], ensure_ascii=False, indent=1))
    if g and chosen:
        ids = {n["id"] for n in g["nodos"] if set(n.get("dominios", [])) & set(chosen)}
        names = {n["id"]: n["nombre"] for n in g["nodos"]}
        rel = [f'- {names[e["de"]]} {e["relacion"]} {names[e["a"]]}: {e["porque"]}'
               for e in g["aristas"] if e["de"] in ids or e["a"] in ids]
        parts.append("## Conexiones relevantes\n" + "\n".join(rel))
    return "\n\n".join(parts)


def choose(question):
    doms = domains()
    index = {k: v.get("resumen", "") for k, v in doms.items()}
    r = claude_json(
        "Elige que dominios del contexto personal necesita esta pregunta para responderse bien (incluye "
        "dominios conectados si la respuesta depende de ellos; ninguno si es una pregunta generica). "
        f'Responde SOLO JSON: {{"dominios": [...], "razon": "..."}}\n\nPregunta: {question}\n\nDominios: '
        + json.dumps(index, ensure_ascii=False))
    return r["dominios"], r.get("razon", "")


def cmd_contexto(a):
    if a.dominios == ["todo"]:
        chosen = list(domains())
    elif a.dominios:
        chosen = a.dominios
    elif a.pregunta:
        chosen, why = choose(a.pregunta)
        print(f"<!-- dominios elegidos: {chosen} ({why}) -->", file=sys.stderr)
    else:
        print("Dominios disponibles:", ", ".join(domains()))
        return
    print(build_context(a.pregunta, chosen))


def cmd_preguntar(a):
    if a.dominios == ["ninguno"]:
        ctx = ""
    else:
        chosen = list(domains()) if a.dominios == ["todo"] else a.dominios or choose(a.pregunta)[0]
        print(f"[contexto: {chosen}]", file=sys.stderr)
        ctx = build_context(a.pregunta, chosen)
    print(claude(f"Contexto personal del usuario (usalo con criterio, sin citarlo textualmente):\n\n{ctx}\n\n"
                 f"---\nPregunta: {a.pregunta}", model=a.modelo))


def cmd_instalar(a):
    d = Path.home() / ".claude" / "skills" / "mi-perfil"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"""---
name: mi-perfil
description: Carga contexto del perfil personal del usuario (necesidades, patrones, conexiones entre sus areas de vida) eligiendo solo los dominios relevantes a la pregunta. Usar cuando la pregunta dependa de quien es el usuario, su musica, su orden/planificacion, bienestar o decisiones personales.
---
1. Lista los dominios: `python3 {ROOT/'perfil.py'} contexto`
2. Elige los relevantes (o deja que se elijan solos) y obtén el contexto:
   `python3 {ROOT/'perfil.py'} contexto --dominios musica orden-planificacion` o
   `python3 {ROOT/'perfil.py'} contexto "<pregunta>"`
   (`--dominios todo` para el panorama completo; no cargues nada si la pregunta es generica).
3. Responde usando ese contexto con criterio, sin recitarlo.
""")
    print(f"Skill instalada: {d/'SKILL.md'}  (uso: /mi-perfil)")


def cmd_todo(a):
    cmd_ingest(a)
    if (OUT / "fuentes" / "sin-proyecto").exists() and a.agrupar:
        cmd_agrupar(a)
    a.rehacer = False
    cmd_analizar(a); cmd_conectar(a); cmd_perfil(a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    def add(name, fn, **kw):
        p = sp.add_parser(name, **kw); p.set_defaults(fn=fn); return p
    for n in ("ingest", "todo"):
        p = add(n, cmd_ingest if n == "ingest" else cmd_todo)
        p.add_argument("export", help="zip o carpeta del export de claude.ai")
        p.add_argument("--extra", nargs="*", help="carpetas con notas propias (carpeta = dominio)")
        p.add_argument("--recorte", type=int, default=400, help="caracteres de cada respuesta de Claude")
        if n == "todo":
            p.add_argument("--agrupar", action="store_true", help="repartir chats sin proyecto en dominios")
    add("agrupar", cmd_agrupar)
    add("analizar", cmd_analizar).add_argument("--rehacer", action="store_true")
    add("conectar", cmd_conectar)
    add("perfil", cmd_perfil)
    for n, fn in (("contexto", cmd_contexto), ("preguntar", cmd_preguntar)):
        p = add(n, fn)
        p.add_argument("pregunta", nargs="?", default="")
        p.add_argument("--dominios", nargs="*", help="manual: nombres, 'todo' o 'ninguno'. Sin esto, se elige solo")
        if n == "preguntar":
            p.add_argument("--modelo")
    add("instalar", cmd_instalar)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
