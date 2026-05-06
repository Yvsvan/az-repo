# Handoff — continuar en Claude Code

Este documento resume el estado del repo y exactamente dónde retomar el trabajo
desde Claude Code (terminal).

---

## 1. Cómo abrir Claude Code y retomar

### Pre-requisitos en tu máquina (Windows)

```powershell
# Python 3.10+ (cualquiera de 3.10 / 3.11 / 3.12)
python --version

# Git
git --version

# Claude Code
# Si no lo tienes: instala desde https://claude.com/claude-code
claude --version
```

### Setup del repo localmente

```powershell
cd C:\Users\ivan5\az-repo

# Crear venv y dependencias
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install

# Verificar que todo se instaló bien
pytest -v
```

### Lanzar Claude Code

Dentro del repo:

```powershell
cd C:\Users\ivan5\az-repo
claude
```

Y como primer mensaje, pega el prompt al final de este archivo.

---

## 2. Estado actual del repo

### ✅ Fase 0 — Bootstrap (completa)

- Estructura de carpetas según `PLAN.md`.
- `pyproject.toml` con dependencias y herramientas (ruff, black, pytest, coverage).
- `LICENSE` (MIT), `README.md`, `.gitignore`, `.pre-commit-config.yaml`.
- GitHub Actions: `.github/workflows/ci.yml` y `.github/workflows/release.yml`.
- Paquete `bank_parser` instalable con `pip install -e ".[dev]"`.
- Versionado en `src/bank_parser/_version.py`.
- Smoke tests en `tests/test_smoke.py`.

### ✅ Fase 1 — Core + parser Banamex (completa)

- `src/bank_parser/core/schema.py` — `Movement`, `StatementSummary`, `Statement`, `BankId`.
- `src/bank_parser/core/exceptions.py` — jerarquía completa.
- `src/bank_parser/core/io_layer.py` — lectura de PDF y ZIPs.
- `src/bank_parser/core/bank_detector.py` — fingerprints de los 5 bancos.
- `src/bank_parser/core/pipeline.py` — orquestación end-to-end.
- `src/bank_parser/parsers/base.py` — `BankParser` ABC.
- `src/bank_parser/parsers/_common.py` — helpers (`limpiar_numero`, `extract_rfc`, etc.).
- `src/bank_parser/parsers/banamex.py` — parser Banamex funcionando.
- `tests/test_io_layer.py`, `tests/test_pipeline.py` — tests de IO y pipeline.
- Golden file: `samples/golden/banamex_micuenta_abr2026.json`.
- `--cov-fail-under=70`, cobertura actual 80.54%.

### ✅ Fase 2 — Parsers de los 4 bancos restantes (completa)

**67 tests pasan, 0 fallan. Cobertura: 80.54%.**

---

### ✅ Fase 3 — Exportador Excel + JSON (completa)

**98 tests pasan, 0 fallan. Cobertura: 82.82%.**

---

### ✅ Fase 4 — GUI CustomTkinter (completa)

**131 tests pasan, 0 fallan. Cobertura: 82.61%.**

---

### ✅ Fase 5 — Auto-update + Packaging (completa)

**150 tests pasan, 0 fallan. Cobertura: 82.61%. Build local: `dist/BankParser/BankParser.exe` 80 MB.**

#### Banorte (`src/bank_parser/parsers/banorte.py`)
- ZIP con un solo PDF (`0660792468_20260131.PDF`).
- Fecha: `DD-MMM-YY` (2 dígitos de año) pegada directamente a la descripción.
- Saldo inicial de `Saldo inicial del periodo $X`.
- Saldo final de `Saldo actual $X`, total abonos de `Total de depósitos $X`.
- Sección: `FECHA DESCRIPCIÓN / ESTABLECIMIENTO...` → `INVERSION ENLACE NEGOCIOS`.
- **Resultado:** 30 movimientos, cuadre OK.

#### BanBajío (`src/bank_parser/parsers/banbajio.py`)
- PDF directo, Cuenta Conecta.
- Fecha: `D MMM` o `DD MMM` (día + mes abreviado en español).
- Resumen en línea con 4 cifras: `$ini $dep $car $fin`.
- **Resultado:** 31 movimientos, cuadre OK.

#### Banregio (`src/bank_parser/parsers/banregio.py`)
- PDF de 21 páginas, varias cuentas (CUENTA NARANJA + REGIOCREDITO).
- Fecha: sólo el día (1–31); mes/año del encabezado del periodo.
- `saldo_final` extraído de `= Saldo Final $X` en la sección Gráfico Transaccional.
- `total_cargos` / `total_abonos` extraídos de la línea `Total X Y Z` de la tabla.
- RFC del cliente de `RFC: XXXX` (con dos puntos); el RFC del banco `R.F.C. BRM...` se ignora.
- **Resultado:** 167 movimientos. Cuadre a nivel de resumen OK. Se producen 2 warnings
  conocidos: Banregio cobra **440.80 en comisiones** que no aparecen como líneas
  individuales en la tabla de movimientos (sólo en el Gráfico). Esto es comportamiento
  documentado del formato y se verifica explícitamente en `test_cuadre_warnings_conocidos`.

#### BBVA (`src/bank_parser/parsers/bbva.py`)
- PDF de 10 páginas, CASH MANAGEMENT M.N.
- Usa `pdfplumber.extract_words()` con coordenadas `x1` para distinguir columnas
  CARGOS / ABONOS / SALDO (no diferenciables con texto plano).
- Los límites de columna se detectan **sólo desde la línea de encabezado de la
  tabla de movimientos** (`OPER LIQ COD. ... CARGOS ABONOS OPERACIÓN LIQUIDACIÓN`).
  Usar `{last-occurrence}` fallaba en la última página donde el resumen repite
  las etiquetas CARGOS/ABONOS en una posición diferente.
- **Resultado:** 86 movimientos, cuadre OK.

---

### ✅ Fase 6 — Polish & docs (completa)

**152 tests pasan, 0 fallan. Cobertura: 82.68%.**

#### Cambios entregados

- `src/bank_parser/__init__.py` — expone `parse_pdf(path)` + `__all__` completo.
- `tests/test_smoke.py` — nuevos tests: `test_public_api_exports`, `test_parse_pdf_convenience`.
- `src/bank_parser/gui/app.py` — título con versión semver, carga de icono silenciosa.
- `README.md` — reescrito completamente: instalación, uso GUI/CLI/API, tablas, arquitectura.
- `docs/architecture.md` — diagrama ASCII completo + descripción de módulos.
- `docs/adding_a_new_bank.md` — guía paso a paso (6 pasos con código).
- `docs/format_drift.md` — 3 capas de detección + flujos de acción.
- `docs/release_process.md` — proceso de tag, CI, publicación, hotfix, semver.
- `CHANGELOG.md` — entrada `[0.1.0]` completa.

---

## 3. Siguiente tarea — Publicar v0.1.0

```powershell
git add -A
git commit -m "Fase 6: polish, docs, CHANGELOG — v0.1.0 ready"
git tag v0.1.0
git push origin main --tags
```

El workflow `release.yml` construirá el `.exe`, lo empaquetará en
`BankParser-v0.1.0-win64.zip` + `.sha256` y publicará el release en GitHub.

### Prompt sugerido para retomar (si se necesita)

> Estoy retomando el parser de estados de cuenta bancarios mexicanos.
> Lee `HANDOFF.md` para ver el estado actual. El proyecto está en `v0.1.0`
> con las 6 fases completas. Indica qué hacer a continuación (soporte a nuevos
> bancos, mejoras de GUI, etc.) o ayúdame con: [describe tu tarea].

### Resumen de la Fase 5 completada

- `src/bank_parser/updater/github_updater.py`:
  - `check_for_update(repo, current_version)` — consulta GitHub API, compara semver con
    `packaging.version`, retorna `UpdateInfo` o `None`. Nunca lanza excepciones.
  - `UpdateInfo` dataclass: `current`, `latest`, `download_url`, `sha256_url`,
    `release_url`, propiedad `is_newer`, propiedad `display_message`.
  - `download_release(info, dest_dir)` — descarga el ZIP, verifica SHA-256 (fail-open si
    el archivo .sha256 no está disponible).
  - `open_release_page(info)` — abre el navegador en la página del release.
  - 19 tests con requests mockeado (sin red real): casos OK, sin update, errores de red,
    JSON malformado, tag inválido, sin assets.
- `src/bank_parser/gui/app.py` actualizado:
  - Llama `check_for_update` en hilo de fondo 2 s después del arranque.
  - Si hay update, muestra botón amarillo "↻ vX.Y.Z disponible" en el header.
  - Al hacer clic → diálogo de confirmación → `open_release_page`.
- `build/pyinstaller.spec` — spec onedir completo:
  - `collect_data_files("customtkinter")` + `collect_data_files("tkinterdnd2")` para
    incluir themes y DLLs nativas.
  - Hidden imports de openpyxl, pydantic v2, pdfminer, tkinterdnd2.
  - `console=False` (sin ventana negra), ícono embebido.
  - **Build local verificado: `dist/BankParser/BankParser.exe` 80 MB (onedir).**
- `build/icon.ico` — ícono azul corporativo (#1F4E79), 4 tamaños (16/32/48/256 px).
- `build/version_info.txt` — metadata PE de Windows (FileVersion, ProductName, etc.).
- `.github/workflows/release.yml` actualizado: también reemplaza versión en
  `build/version_info.txt` al taggear.

### Para publicar el primer release

```powershell
git add -A
git commit -m "Fase 5: auto-update + packaging"
git tag v0.1.0
git push origin main --tags
```

El workflow `release.yml` construirá el `.exe`, lo comprimirá en
`BankParser-v0.1.0-win64.zip` con su `.sha256` y publicará el release en GitHub.

### Resumen de la Fase 4 completada

- `src/bank_parser/gui/app_state.py` — modelo de estado puro (sin tkinter), con
  `FileEntry` y `AppState`. 33 tests unitarios.
- `src/bank_parser/gui/theme.py` — paleta de colores y configuración CTK.
- `src/bank_parser/gui/widgets/drop_zone.py` — zona de arrastre + botón "Seleccionar".
  Drag-and-drop vía `tkinterdnd2` (graceful degradation si no está disponible).
- `src/bank_parser/gui/widgets/file_list.py` — lista de archivos con iconos de estado,
  metadata (banco / RFC / conteo de movimientos / advertencias) y botón de borrado.
- `src/bank_parser/gui/widgets/progress_log.py` — log con timestamps y colores por nivel
  (ok=verde, warn=amarillo, error=rojo).
- `src/bank_parser/gui/widgets/preview_table.py` — ttk.Treeview con filtro por RFC.
- `src/bank_parser/gui/app.py` — ventana principal `BankParserApp(ctk.CTk)`:
  - Drag-and-drop compatible con `tkinterdnd2.DnDWrapper`.
  - Pipeline corre en hilos de fondo (`threading.Thread`); resultados via `queue.Queue`
    drenada con `after(100, poll)` para no bloquear la UI.
  - Botones **Procesar**, **Exportar .xlsx** y **Exportar .json** con estado
    (disabled/normal) reflejando el estado de `AppState`.
  - Preview toggle (muestra/oculta `PreviewTable`).
  - Selector de carpeta de salida.
- `src/bank_parser/cli.py` — actualizado para soportar `-o archivo.xlsx` además de `.json`.

### Resumen de la Fase 3 completada

- `src/bank_parser/exporters/excel.py` — exporta a `.xlsx` con openpyxl.
  - Una hoja por RFC (nombre = RFC o `SIN_RFC_N` si no hay RFC).
  - Consolidación automática de múltiples Statements del mismo RFC.
  - Columnas fijas: `fecha`, `descripcion`, `abono`, `cargo`, `saldo`, `banco`,
    `cuenta`, `archivo_origen`.
  - Encabezados en negrita con fondo azul corporativo; números con formato `#,##0.00`.
  - Fila **TOTAL** al pie (suma de abonos y cargos) con fondo diferenciado.
  - Hoja **Resumen** con una fila por Statement y metadatos completos.
  - Hoja **Advertencias** (sólo si hay warnings en algún Statement).
  - Columnas autoajustadas al contenido.
- `src/bank_parser/exporters/json_exporter.py` — serialización JSON vía pydantic.
  - `export_to_json(statements, path)` — lista de Statements.
  - `export_single_to_json(statement, path)` — un Statement sin envolver en lista.
- 31 tests en `tests/test_exporters/` (23 Excel + 8 JSON), todos pasan.

---

## 4. Decisiones ya tomadas (no re-preguntar)

- **GUI:** CustomTkinter con drag-and-drop.
- **Salida:** Excel (.xlsx) y JSON.
- **Distribución:** `.exe` standalone vía GitHub Releases con auto-update al iniciar.
- **Procesamiento:** un PDF a la vez, auto-extracción de ZIPs, salida consolidada
  por RFC con columna de banco.
- **Schema de columnas:** mínimo estandarizado (`fecha`, `descripcion`, `abono`,
  `cargo`, `saldo`, `banco`, `cuenta`, `archivo_origen`).

---

## 5. Notas técnicas / gotchas detectados

1. **Banamex tiene una sub-sección "AHORRO FACIL"** en algunos PDFs. El parser
   actualmente sólo procesa la sección "MiCuenta" (la principal) y corta antes
   de "AHORRO FACIL". Si un cliente usa AHORRO FACIL, hay que agregar lógica
   de "una cuenta = un Statement" y procesar ambas.

2. **Filtrado de page-headers:** los PDFs paginan con un footer y re-imprimen el
   header de columnas en cada página nueva. Esos artefactos se filtran en
   `_strip_noise()` de cada parser. Si un banco cambia el formato de su footer,
   hay que actualizar `_NOISE_PATTERNS`.

3. **Banregio: comisiones fuera del detalle.** Los 440.80 en cargos son cobros
   de comisión que Banregio contabiliza en el resumen pero no lista como líneas
   individuales en la tabla DIA CONCEPTO. El cuadre a nivel de resumen es correcto;
   el cuadre de movimientos produce 2 warnings esperados (documentados en el test).

4. **BBVA: última página con resumen.** La última página de movimientos del BBVA
   Cash Management incluye un resumen/pie donde las etiquetas CARGOS y ABONOS
   aparecen con coordenadas distintas a las del encabezado de la tabla. Si la
   detección de bounds usara el **último** valor de cada etiqueta (dict comprehension
   normal), los límites de columna serían erróneos y 304,981 MXN en abonos se
   perderían. La solución (en `bbva.py`) es detectar bounds sólo desde la línea
   de encabezado que empieza con "OPER".

5. **Detección por fingerprints:** el `bank_detector` cuenta matches y resuelve
   ambigüedad por el score más alto. Para los samples actuales, los `must_have`
   de cada banco son lo suficientemente específicos. Si en el futuro hay
   ambigüedad, el error es claro y la GUI ofrecerá selección manual.

---

## 6. Cuando lleguen estados de cuenta nuevos

Los samples actuales son **el contrato del parser**. Cuando un banco cambie su
plantilla:

1. El `format_drift` (capa 1 — `expected_markers`) **probablemente** detecte el
   cambio y lance `FormatChangedError` con el marcador faltante.
2. Si no, el cuadre numérico (capa 2) generará un warning visible.
3. La acción es: agregar el PDF nuevo a `samples/<banco>/`, ajustar el parser
   (sus regex/markers), regenerar el golden con `pytest --regen-golden` y
   commitear todo junto.

---

## 7. Comandos útiles de día a día

```powershell
# Lint y format
ruff check src tests --fix
black src tests

# Tests con cobertura
pytest -v

# Tests sólo de un parser
pytest tests/test_parsers/test_bbva.py -v

# Regenerar golden files (después de un cambio legítimo)
pytest --regen-golden

# Probar el parser desde CLI
python -m bank_parser samples\banamex\banamex_micuenta_abr2026.pdf
python -m bank_parser samples\banamex\banamex_micuenta_abr2026.pdf -o out\salida.json

# Build local del .exe (Fase 5+)
pyinstaller build\pyinstaller.spec --noconfirm

# Crear un release
git tag v0.1.0
git push origin v0.1.0   # dispara .github/workflows/release.yml
```

---

## 8. Prompt para retomar en nueva sesión

> Estoy retomando el desarrollo de un parser de estados de cuenta bancarios
> mexicanos en PDF. Lee `PLAN.md` (plan completo), `HANDOFF.md` (estado actual)
> y `README.md`. Luego dime un breve resumen del estado y procede con la
> **Fase 6: Polish & docs** (README con quick-start, `docs/`, primera publicación
> del release `v0.1.0`). Actualiza `HANDOFF.md` al terminar.

---

*Fase 5 completa. 150 tests, 0 fallos, 82.61% cobertura. Build exe local verificado (80 MB onedir).*
