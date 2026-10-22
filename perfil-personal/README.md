# Perfil personal interconectado

1. En claude.ai: Settings → Privacy → **Export data**. Descarga el zip (queda fuera de git).
2. Pipeline completo:
   ```
   python3 perfil-personal/perfil.py todo ~/Descargas/export.zip --agrupar
   ```
   o paso a paso: `ingest` → `agrupar` → `analizar` → `conectar` → `perfil`.
3. Resultados en `perfil-personal/salida/`: `PERFIL.md`, `grafo.md` (mapa mermaid), `dominios/*.json`.
4. Elegir contexto por pregunta:
   ```
   perfil.py contexto "¿cómo organizo mi semana de composición?"        # elige dominios solo
   perfil.py preguntar "..." --dominios musico orden-planificacion      # manual
   perfil.py preguntar "..." --dominios todo | ninguno
   perfil.py instalar                                                   # crea la skill /mi-perfil
   ```

Notas: necesita `claude` CLI. Los datos se envían a Claude para analizarse (igual que en tus chats). `salida/` y `export/` están en `.gitignore`. Si tu export no enlaza chats con proyectos, `agrupar` los clasifica por tema; puedes sumar notas propias con `--extra carpeta/`.
