# Arquitectura del Sistema

## Visión general

```
┌─────────────────────────────────────────────────────────────────┐
│                    GUI (CustomTkinter)                          │
│  drag-and-drop  ·  log de progreso  ·  preview  ·  exportar    │
└──────────────────────────┬──────────────────────────────────────┘
                           │  process_file(path)
              ┌────────────▼─────────────┐
              │      Pipeline (core)     │
              │  Input → Detect → Parse  │
              │       → Validate → Export│
              └────┬───────────┬─────────┘
                   │           │
       ┌───────────▼──┐   ┌────▼────────────┐
       │  io_layer    │   │  bank_detector  │
       │  PDF & ZIP   │   │  fingerprints   │
       └──────────────┘   └────┬────────────┘
                               ▼
                ┌──────────────────────────┐
                │   parsers/  (registry)   │
                │   ├ banamex.py           │
                │   ├ bbva.py              │
                │   ├ banbajio.py          │
                │   ├ banregio.py          │
                │   └ banorte.py           │
                └──────┬───────────────────┘
                       │
                ┌──────▼──────────────────┐
                │  schema  (pydantic)     │
                │  Movement, Statement    │
                └──────┬──────────────────┘
                       │
                ┌──────▼──────────────────┐
                │  validators             │
                │  · cuadre numérico      │
                │  · format-drift         │
                └──────┬──────────────────┘
                       │
                ┌──────▼──────────────────┐
                │  exporters              │
                │  · xlsx (openpyxl)      │
                │  · json (pydantic)      │
                └─────────────────────────┘
```

---

## Módulos principales

### `core/schema.py` — Modelos de datos

Tres modelos pydantic v2 (inmutables con `frozen=True`):

- **`Movement`** — una transacción: fecha, descripción, abono, cargo, saldo, banco, cuenta, archivo.
- **`StatementSummary`** — metadatos del estado de cuenta: titular, RFC, periodo, saldo inicial/final, totales.
- **`Statement`** — la unión: `summary + movements + warnings`.
- **`BankId`** — enum `str` con los 5 bancos soportados y su `display_name`.

Todos los importes son `Decimal` (nunca `float`) para evitar errores de redondeo financiero.

### `core/io_layer.py` — Ingesta de archivos

- `extract_pdfs_from_input(path)` — acepta un PDF directo o un ZIP con uno o varios PDFs adentro. Devuelve lista de `PdfFile(nombre, contenido_bytes)`.
- `read_pdf_text(pdf_bytes)` — extrae el texto completo con `pdfplumber`. Lanza `UnsupportedFileError` si el PDF parece escaneado (sin texto extraíble).

### `core/bank_detector.py` — Detección de banco

Cada banco tiene un conjunto de `must_have` (strings obligatorios) y `boost` (strings que aumentan el score). La función `detect_bank(text)` evalúa todos los bancos y retorna el `BankId` con mayor score. Si el score es 0 o hay empate → `BankDetectionError`.

### `parsers/<banco>.py` — Parsers específicos

Cada parser hereda de `BankParser` (ABC) e implementa:

```python
def parse(self, text: str, *, pdf_bytes: bytes, archivo_origen: str) -> Statement: ...
```

Estrategia general:
1. Verificar `expected_markers` (estructura esperada del PDF).
2. Extraer metadatos del encabezado (RFC, titular, cuenta, periodo, saldos).
3. Iterar las líneas de la tabla de movimientos con regex.
4. Construir y devolver el `Statement`.

Particularidades por banco:

| Banco | Técnica |
|---|---|
| Banamex | Regex sobre texto plano; inferencia abono/cargo por variación de saldo |
| BBVA | `pdfplumber.extract_words()` con coordenadas X para separar columnas CARGOS/ABONOS/SALDO |
| BanBajío | Split por fecha; los montos son las últimas 1-3 cifras del renglón |
| Banregio | El día viene sin mes (se toma del encabezado del periodo) |
| Banorte | ZIP con un PDF; fecha `DD-MMM-YY` pegada a la descripción |

### `validators/balance.py` — Cuadre numérico

`validar_cuadre(statement)` comprueba:
- `saldo_inicial + Σabonos − Σcargos ≈ saldo_final` (tolerancia 0.01 MXN).
- `Σabonos` calculado ≈ `total_abonos` del PDF (y lo mismo para cargos).

Los errores se devuelven como `list[str]` (warnings) y se adjuntan al `Statement`.

### `exporters/excel.py` — Exportación a .xlsx

`export_to_xlsx(statements, path)`:
- Agrupa por RFC; una hoja por RFC.
- Columnas fijas en orden canónico.
- Fila TOTAL al pie con suma de abonos y cargos.
- Hoja **Resumen** con metadatos de cada Statement.
- Hoja **Advertencias** (condicional).

### `exporters/json_exporter.py` — Exportación a .json

`export_to_json(statements, path)` usa `statement.model_dump_json()` de pydantic, que serializa correctamente `Decimal` y `date`.

### `updater/github_updater.py` — Auto-actualización

`check_for_update(repo, current_version)`:
- Consulta `GET https://api.github.com/repos/{repo}/releases/latest`.
- Compara versiones con `packaging.version.Version`.
- Retorna `UpdateInfo | None`. Nunca lanza excepciones.

---

## Patrones de diseño usados

### Registry de parsers

```python
BANK_REGISTRY: dict[BankId, type[BankParser]] = {
    BankId.BANAMEX: BanamexParser,
    ...
}
```

Agregar un banco = un archivo + una línea. El pipeline no cambia.

### Separación UI / lógica

`AppState` (en `gui/app_state.py`) contiene toda la lógica de estado sin dependencias de tkinter. Los widgets leen de `AppState` y llaman sus métodos. Esto permite testear la lógica sin display.

### Threading model en la GUI

El pipeline corre en hilos de fondo (`threading.Thread`). Los resultados se pasan al hilo principal vía `queue.Queue` y se procesan con `widget.after(100, poll_fn)`. Tkinter no es thread-safe; nunca se toca un widget desde un hilo de fondo.

---

## Dependencias clave

| Paquete | Versión mínima | Uso |
|---|---|---|
| `pdfplumber` | 0.11 | Extracción de texto y coordenadas de PDFs |
| `pydantic` | 2.6 | Modelos de datos, validación, serialización JSON |
| `openpyxl` | 3.1 | Generación de archivos .xlsx |
| `customtkinter` | 5.2 | GUI con apariencia moderna |
| `tkinterdnd2` | 0.4 | Drag-and-drop de archivos |
| `requests` | 2.31 | Check de actualizaciones (GitHub API) |
| `packaging` | 23.2 | Comparación semver |

---

## Tests

| Suite | Qué cubre |
|---|---|
| `test_smoke.py` | Imports, semver, API pública |
| `test_bank_detector.py` | Fingerprints y resolución de ambigüedades |
| `test_parsers/test_*.py` | Parser de cada banco + golden regression |
| `test_exporters/test_excel.py` | Estructura del xlsx, columnas, totales |
| `test_exporters/test_json.py` | Serialización JSON, UTF-8, lista/single |
| `test_gui_state.py` | `AppState` y `FileEntry` sin GUI |
| `test_updater.py` | `check_for_update` con `requests` mockeado |

Cobertura total: ≥82 %. Los módulos `gui/*` y `updater/*` están excluidos del
threshold de cobertura (difíciles de testear sin display/red real).
