# Changelog

Todos los cambios notables de este proyecto se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).
Este proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

---

## [0.1.0] — 2026-05-05

Primera versión pública del sistema.

### Added

**Parsers bancarios (5 bancos)**
- **Banamex** (Citibanamex) — MiCuenta: extracción con regex + inferencia
  de abono/cargo por variación de saldo.
- **BBVA México** — Cash Management M.N.: detección de columnas CARGOS/ABONOS/SALDO
  por coordenadas X con `pdfplumber.extract_words()`.
- **BanBajío** — Cuenta Conecta: split por línea de fecha; montos como
  últimas cifras del renglón.
- **Banregio** — Cuenta Naranja Negocios: días sin mes (inferidos del periodo
  del encabezado).
- **Banorte** — Enlace Negocios: ZIP con un PDF; fechas `DD-MMM-YY` pegadas
  a la descripción.

**Core**
- `core/schema.py` — modelos pydantic v2 inmutables (`Movement`, `StatementSummary`,
  `Statement`, `BankId`); todos los importes como `Decimal`.
- `core/io_layer.py` — ingesta de PDF directo o ZIP con múltiples PDFs.
- `core/bank_detector.py` — fingerprints con `must_have` + `boost` scoring.
- `core/pipeline.py` — orquesta detección → parseo → validación.
- `core/exceptions.py` — jerarquía de errores (`BankParserError`, `FormatChangedError`,
  `ParseError`, `BankDetectionError`, `UnsupportedFileError`).

**Validación**
- `validators/balance.py` — cuadre numérico con tolerancia 0.01 MXN; warnings
  no bloquean la salida.

**Exportadores**
- `exporters/excel.py` — `.xlsx` con una hoja por RFC, columnas canónicas,
  fila TOTAL, hoja Resumen, hoja Advertencias condicional.
- `exporters/json_exporter.py` — serialización JSON con `Decimal` y `date`
  correctamente codificados, UTF-8, sin `ensure_ascii`.

**GUI**
- Interfaz CustomTkinter (tema oscuro, paleta azul corporativa).
- Drag-and-drop de PDFs y ZIPs (tkinterdnd2).
- Log de progreso con timestamps y colores por nivel.
- Tabla de preview filtrable por RFC.
- Procesamiento en hilos de fondo; UI nunca se bloquea.
- Botón de exportación `.xlsx` y `.json`.

**CLI**
- `python -m bank_parser <archivo>` con flags `-o` (output).
- Soporta `.pdf`, `.zip`, salida `.xlsx` y `.json`.

**Auto-updater**
- Consulta GitHub Releases API al iniciar; muestra banner si hay versión nueva.
- `updater/github_updater.py` — nunca lanza excepciones; fail-open en red.

**API Python pública**
- `bank_parser.parse_pdf(path)` — atajo de alto nivel.
- `bank_parser.BankId`, `Statement`, `StatementSummary`, `Movement` en `__all__`.

**Packaging**
- Build con PyInstaller (onedir, sin consola) para Windows 10/11 x64.
- Workflow `release.yml` — genera `.zip` + `.sha256` en GitHub Releases al
  pushear un tag `v*`.

**Docs**
- `README.md` — instalación, uso GUI/CLI/API, arquitectura, contribución.
- `docs/architecture.md` — diagrama y descripción de cada módulo.
- `docs/adding_a_new_bank.md` — guía paso a paso para añadir un banco.
- `docs/format_drift.md` — sistema de detección de cambios de formato.
- `docs/release_process.md` — proceso de publicación de versiones.

**Tests**
- Suite con ≥ 82 % de cobertura.
- Golden-file regression para cada banco.
- Flag `--regen-golden` para regenerar golden files.
- Tests unitarios: smoke, bank_detector, exporters (excel + json),
  pipeline, io_layer, updater, app_state.
