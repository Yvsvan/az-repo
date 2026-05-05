# Plan de Desarrollo — Parser de Estados de Cuenta Bancarios

> **Proyecto:** App de escritorio para parsear estados de cuenta de bancos mexicanos en PDF y producir tablas estandarizadas de movimientos.
> **Repositorio:** `az-repo` (este folder será la raíz del repo de GitHub).
> **Fecha del plan:** 2026-05-04
> **Autor:** Equipo de consultoría contable.

---

## 1. Resumen ejecutivo

Una app de escritorio (Windows-first, distribuida como `.exe`) que recibe un PDF (o ZIP con uno o varios PDFs adentro) de estado de cuenta bancario, identifica automáticamente al banco emisor, ejecuta un parser específico para ese banco, y exporta los movimientos (abonos / cargos) en formato tabular estandarizado. La app valida el cuadre del estado de cuenta y advierte explícitamente si el formato del PDF no coincide con el esperado (señal de que el banco cambió la plantilla y hay que actualizar el parser).

---

## 2. Decisiones de producto (acordadas)

| Tema | Decisión |
|------|----------|
| Interfaz | App de escritorio (GUI) con **CustomTkinter** |
| Salida | **Excel (.xlsx)** y **JSON** simultáneamente |
| Distribución | **Ejecutable standalone (.exe)** vía GitHub Releases |
| Auto-update | **Auto-check al iniciar** contra GitHub Releases |
| Modo de procesamiento | Un PDF a la vez, **auto-extracción de ZIPs**, salida consolidada cuando los PDFs son del mismo titular |
| Identificación de titular | **Por RFC** extraído del PDF |
| Esquema de columnas | **Mínimo estandarizado** (igual para todos los bancos) |

---

## 3. Bancos soportados y fingerprints de detección

Cada banco tiene un layout completamente distinto. La detección se hace con **fingerprints en el texto** de las primeras 1–2 páginas. El plan inicial cubre 5 bancos (todos los presentes en `samples/`).

| Banco | Fingerprint primario | Fingerprint secundario | Parser |
|-------|---------------------|------------------------|--------|
| **Banamex** (Citibanamex) | `"MiCuenta"` + `"banamex"` | Header de tabla `FECHA CONCEPTO RETIROS DEPÓSITOS SALDO`; fecha `DD MMM` (ej. `13 MAR`) | `parsers/banamex.py` |
| **BBVA** México | `"BBVA MEXICO"` + `"Cash Management"` | Header `OPER LIQ COD. DESCRIPCIÓN REFERENCIA CARGOS ABONOS OPERACIÓN LIQUIDACIÓN`; fecha `DD/MMM` | `parsers/bbva.py` |
| **BanBajío** | `"BANCO DEL BAJIO"` + `"CUENTA CONECTA BANBAJIO"` | Header `FECHA DESCRIPCION ... DEPOSITOS RETIROS SALDO`; fecha `D MMM` | `parsers/banbajio.py` |
| **Banregio** | `"Banco Regional"` + `"Banregio Grupo Financiero"` | Header `DIA CONCEPTO CARGOS ABONOS SALDO`; fecha sólo día (mes en encabezado del periodo) | `parsers/banregio.py` |
| **Banorte** | `"BANORTE"` + `"ENLACE NEGOCIOS"` | Header `FECHA DESCRIPCIÓN / ESTABLECIMIENTO MONTO DEL DEPOSITO MONTO DEL RETIRO SALDO`; fecha `DD-MMM-YY` | `parsers/banorte.py` |

> **Estrategia de detección:** función `detect_bank(text)` evalúa los fingerprints en orden de especificidad y devuelve un `BankId` (enum). Si hay 0 ó >1 matches, lanza `BankDetectionError` para que la GUI muestre un diálogo con la lista de bancos soportados y permita selección manual.

---

## 4. Arquitectura — visión general

```
┌─────────────────────────────────────────────────────────────────┐
│                          GUI (CustomTkinter)                    │
│   drag-and-drop  ·  log de progreso  ·  preview tabla  ·  export│
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────▼─────────────┐
              │      Pipeline (core)     │
              │  Input → Detect → Parse  │
              │       → Validate → Export│
              └────┬───────────┬─────────┘
                   │           │
       ┌───────────▼──┐   ┌────▼────────────┐
       │  io_layer    │   │  bank_detector  │
       │ (PDF & ZIP   │   │  (fingerprints) │
       │  ingestion)  │   └────┬────────────┘
       └──────────────┘        │
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
                │  · cuadre saldo inicial │
                │  · cuadre suma          │
                │  · totales del PDF      │
                │  · # de filas esperadas │
                └──────┬──────────────────┘
                       │
                ┌──────▼──────────────────┐
                │  exporters              │
                │  · xlsx (openpyxl)      │
                │  · json                 │
                └─────────────────────────┘
```

### Patrón clave: **registry de parsers**

Cada parser implementa la misma interfaz (`BankParser` ABC). Se registran en un diccionario `BANK_REGISTRY: dict[BankId, type[BankParser]]`. **Agregar un nuevo banco = un archivo nuevo + una línea en el registro.** No hay que tocar el resto de la app.

---

## 5. Estructura de carpetas propuesta

```
az-repo/
├── README.md                       ← Quick-start para usuarios y devs
├── PLAN.md                         ← este documento
├── LICENSE
├── pyproject.toml                  ← config del proyecto (deps, build)
├── .gitignore
├── .github/
│   └── workflows/
│       ├── ci.yml                  ← lint + tests en cada push
│       └── release.yml             ← build .exe y publicar release al taggear vX.Y.Z
├── src/
│   └── bank_parser/
│       ├── __init__.py
│       ├── __main__.py             ← entrypoint (lanza GUI)
│       ├── _version.py             ← versión semántica única
│       ├── core/
│       │   ├── pipeline.py         ← orquesta detect→parse→validate→export
│       │   ├── bank_detector.py    ← fingerprints + detect_bank()
│       │   ├── io_layer.py         ← PDF read (pdfplumber), ZIP extract, validaciones
│       │   ├── schema.py           ← Movement, Statement, BankId (pydantic + Enum)
│       │   └── exceptions.py       ← BankDetectionError, FormatChangedError, etc.
│       ├── parsers/
│       │   ├── __init__.py         ← BANK_REGISTRY
│       │   ├── base.py             ← class BankParser(ABC)
│       │   ├── banamex.py
│       │   ├── bbva.py
│       │   ├── banbajio.py
│       │   ├── banregio.py
│       │   ├── banorte.py
│       │   └── _common.py          ← helpers: limpiar_numero, parse_fecha_es, etc.
│       ├── validators/
│       │   ├── __init__.py
│       │   ├── balance.py          ← cuadre saldo_inicial + Σabonos − Σcargos = saldo_final
│       │   ├── totals.py           ← compara totales extraídos vs sumatorios
│       │   └── format_drift.py     ← detección de cambios de formato
│       ├── exporters/
│       │   ├── __init__.py
│       │   ├── xlsx_exporter.py    ← .xlsx con hojas Movimientos / Resumen / Metadatos
│       │   └── json_exporter.py
│       ├── gui/
│       │   ├── __init__.py
│       │   ├── app.py              ← root window CustomTkinter
│       │   ├── widgets/
│       │   │   ├── drop_zone.py
│       │   │   ├── progress_log.py
│       │   │   ├── preview_table.py
│       │   │   └── settings_panel.py
│       │   └── theme.py
│       └── updater/
│           ├── __init__.py
│           └── github_updater.py   ← consulta GitHub Releases, compara semver, descarga
├── tests/
│   ├── conftest.py
│   ├── test_bank_detector.py
│   ├── test_parsers/
│   │   ├── test_banamex.py
│   │   ├── test_bbva.py
│   │   ├── test_banbajio.py
│   │   ├── test_banregio.py
│   │   └── test_banorte.py
│   ├── test_validators.py
│   └── test_pipeline.py
├── samples/                        ← PDFs de muestra (los que ya tienes)
│   ├── banamex/
│   ├── bbva/
│   ├── banbajio/
│   ├── banregio/
│   ├── banorte/
│   └── golden/                     ← outputs esperados (.json) por sample, para regression tests
├── build/
│   ├── pyinstaller.spec            ← config de PyInstaller
│   └── icon.ico
└── docs/
    ├── architecture.md
    ├── adding_a_new_bank.md        ← cómo agregar un parser de banco nuevo
    ├── format_drift.md             ← cómo se detecta y se actualiza un parser
    └── release_process.md
```

---

## 6. Esquema de datos (schema)

```python
# src/bank_parser/core/schema.py
from datetime import date
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel

class BankId(str, Enum):
    BANAMEX = "banamex"
    BBVA = "bbva"
    BANBAJIO = "banbajio"
    BANREGIO = "banregio"
    BANORTE = "banorte"

class Movement(BaseModel):
    fecha: date
    descripcion: str
    abono: Decimal       # 0 si es cargo
    cargo: Decimal       # 0 si es abono
    saldo: Decimal
    banco: BankId
    cuenta: str          # número de cuenta (último identificador)
    archivo_origen: str  # nombre del PDF de origen

class StatementSummary(BaseModel):
    banco: BankId
    titular: str
    rfc: str | None
    cuenta: str
    periodo_inicio: date
    periodo_fin: date
    saldo_inicial: Decimal
    saldo_final: Decimal
    total_abonos: Decimal
    total_cargos: Decimal
    archivo_origen: str

class Statement(BaseModel):
    summary: StatementSummary
    movements: list[Movement]
    warnings: list[str] = []   # ← aquí van las advertencias de format-drift
```

### Columnas estandarizadas (output)

`fecha` · `descripcion` · `abono` · `cargo` · `saldo` · `banco` · `cuenta` · `archivo_origen`

Para salida consolidada (varios PDFs del mismo titular por RFC), se concatenan filas y la columna `banco` permite distinguir.

---

## 7. Parsers por banco — estrategia individual

Cada parser implementa esta interfaz:

```python
class BankParser(ABC):
    bank_id: BankId
    expected_fingerprints: list[str]   # se valida al inicio

    def parse(self, pdf_text: str, pdf_obj: pdfplumber.PDF) -> Statement: ...
```

### 7.1 Banamex (`parsers/banamex.py`)
Reutiliza el approach del `sample.py` (que tu prueba ya validaba sobre Banamex):
- Encontrar `SALDO ANTERIOR` con regex de fecha `\d{2}\s+[A-Z]{3}`.
- Iterar bloques con regex de movimiento `(\d{2}\s+[A-Z]{3})([\s\S]*?)(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d{1,3}(?:,\d{3})*\.\d{2})`.
- Inferir abono vs cargo comparando `saldo_actual` vs `saldo_previo`.
- Año del periodo se obtiene del bloque `Período del DD de mes al DD de mes del AAAA`.

### 7.2 BBVA (`parsers/bbva.py`)
Más complejo: tiene dos fechas (operación + liquidación) y dos columnas de saldo (operación + liquidación). Se va a usar **`pdfplumber.extract_tables()`** en lugar de regex sobre texto plano, ya que BBVA mantiene tablas extraíbles. Fallback a regex si falla.
- Map de columnas: `OPER`, `LIQ`, `COD.`, `DESCRIPCIÓN`, `REFERENCIA`, `CARGOS`, `ABONOS`, `OPERACIÓN`, `LIQUIDACIÓN`.
- Para el `saldo` estandarizado se usa `LIQUIDACIÓN` (saldo de liquidación).
- Una fila lógica puede abarcar varias filas físicas (referencia y subdescripción); se agrupan por presencia de fecha en `OPER`.

### 7.3 BanBajío (`parsers/banbajio.py`)
- Header: `FECHA DESCRIPCION DE LA OPERACION DEPOSITOS RETIROS SALDO`.
- Cada movimiento: línea con fecha + número de referencia + descripción base, seguida de **N líneas de detalle** (`INSTITUCIÓN EMISORA`, `ORDENANTE`, `CUENTA ORDENANTE`, `REFERENCIA`, `HORA`, `CLAVE DE RASTREO`).
- Estrategia: split por regex de fecha al inicio de línea (`^\d{1,2}\s+[A-Z]{3}\s`), agrupar líneas siguientes hasta la próxima fecha. Extraer los 1, 2 o 3 montos al final del primer renglón (depósitos / retiros / saldo) — los faltantes son `0`.

### 7.4 Banregio (`parsers/banregio.py`)
- Header: `DIA CONCEPTO CARGOS ABONOS SALDO`.
- Solo aparece el día (1–31); el mes y año vienen del título "del 01 al 31 de ENERO 2026".
- Cada movimiento empieza con `\d{2}\s+(TRA|INT|DEP|...)`.
- La descripción puede continuar en líneas siguientes, todas con prefijo en blanco.

### 7.5 Banorte (`parsers/banorte.py`)
- Header: `FECHA DESCRIPCIÓN / ESTABLECIMIENTO MONTO DEL DEPOSITO MONTO DEL RETIRO SALDO`.
- Fecha en formato `DD-MMM-YY` con guiones, en mayúsculas, español.
- Múltiples PDFs en un ZIP, así que el `io_layer` los enumera.
- Cada movimiento incluye múltiples renglones de detalle (`CONCEPTO:`, `REFERENCIA:`, `CVE RAST:`).

### 7.6 Helpers compartidos (`parsers/_common.py`)

```python
MES_ES = {"ENE":1,"FEB":2,"MAR":3,"ABR":4,"MAY":5,"JUN":6,
          "JUL":7,"AGO":8,"SEP":9,"OCT":10,"NOV":11,"DIC":12}

def limpiar_numero(s: str) -> Decimal: ...
def parse_fecha_es(s: str, year_hint: int|None=None) -> date: ...
def extract_rfc(text: str) -> str|None: ...
def extract_cuenta(text: str, patterns: list[str]) -> str|None: ...
```

---

## 8. Detección de cambios de formato (format drift)

Este es uno de los requisitos clave. Tres capas de validación:

### Capa 1 — Validación estructural (al inicio del parser)
Cada parser declara `expected_fingerprints` (encabezados de tabla, marcadores fijos). Si alguno falta → `FormatChangedError("BBVA: header de tabla 'OPER LIQ COD...' no encontrado")`. La GUI muestra un banner rojo: *"El formato de BBVA cambió. El parser necesita ser actualizado. Reporta este PDF al equipo de desarrollo."*

### Capa 2 — Cuadre numérico (post-parse)
- Verificar `saldo_inicial + Σabonos − Σcargos == saldo_final` con tolerancia de `0.01` por redondeos.
- Comparar `Σabonos` y `Σcargos` calculados contra los totales que el propio PDF reporta (todos los bancos los muestran en la sección de resumen). Si difieren → warning.
- Verificar que el número de movimientos sea > 0 si hubo actividad.

Las inconsistencias se devuelven como `Statement.warnings` y se muestran al usuario antes de exportar.

### Capa 3 — Snapshot de hash de plantilla (CI)
Para cada PDF en `samples/`, se guarda un hash SHA-256 del *layout* (set de coordenadas y headers normalizados). Si el hash cambia entre versiones del banco, la suite de tests falla y avisa al equipo. Esto es proactivo: detecta cambios incluso antes de que falle un parse real.

---

## 9. Diseño de la GUI (CustomTkinter)

```
┌──────────────────────────────────────────────────────┐
│  Parser de Estados de Cuenta            [⚙] [↻ v1.2.0]│
├──────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────┐ │
│ │       📄  Suelta tu PDF o ZIP aquí               │ │
│ │           (o haz click para seleccionar)         │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ Archivos cargados:                                   │
│  ✓ EDO CTA BBVA FEB 26.pdf       BBVA   RFC: CEL...  │
│  ✓ EDO CTA BANREGIO ENERO 2026.pdf Banregio RFC:CEL..│
│  ⚠ samples/raro.pdf              [Banco no detectado]│
│                                                      │
│  [Procesar todos]                                    │
│                                                      │
│ Log:                                                 │
│  [10:42:01] BBVA: 87 movimientos, cuadre OK ✓        │
│  [10:42:02] Banregio: 142 mov, cuadre OK ✓           │
│                                                      │
│  Salida:  [.xlsx ✓]  [.json ✓]   📁 az-repo\out\     │
│  [Exportar consolidado por RFC]                      │
└──────────────────────────────────────────────────────┘
```

**Comportamiento:**
- Al soltar archivos, automáticamente: extrae ZIPs, detecta banco, muestra titular/RFC.
- Si hay PDFs de un mismo RFC, se agrupan visualmente.
- Botón **Procesar** corre el pipeline; el log va apareciendo línea por línea.
- Al terminar, se habilitan los botones de exportar (a disco) o "preview tabla" (vista previa de movimientos parseados).
- Banner superior si hay actualización disponible (ver §11).

---

## 10. Build y empaquetado a `.exe`

**Herramienta:** PyInstaller (más simple, ampliamente usado, suficiente para CustomTkinter).

```
build/pyinstaller.spec      # configuración con datos embebidos (icon, samples mínimos, theme)
```

Comando local de build:
```bash
pyinstaller build/pyinstaller.spec --noconfirm
# → dist/BankParser/BankParser.exe (modo onedir, ~80 MB) o BankParser.exe único (~30 MB onefile)
```

**Recomendación:** modo `onedir` para arranque más rápido y mejor manejo por el antivirus de Windows (los `.exe onefile` suelen disparar falsos positivos). Se distribuye un `.zip` con el folder.

---

## 11. Auto-update (al iniciar)

**Mecanismo:**

1. Al lanzar la app, en background se hace `GET https://api.github.com/repos/<user>/az-repo/releases/latest`.
2. Se compara `tag_name` (semver) con `bank_parser._version.__version__`.
3. Si es mayor → toast no-intrusivo en la GUI: *"Versión 1.3.0 disponible. [Actualizar ahora] [Después]"*.
4. Al confirmar:
   - Descarga el `.zip` del release a `%TEMP%`.
   - Extrae junto al ejecutable actual.
   - Lanza un script `updater.bat` (o `.exe` separado) que reemplaza los archivos y reabre la app.
5. Estados manejados: sin internet, GitHub rate-limited, release malformado, descarga corrupta (verificación SHA-256 publicada en el release).

**Módulo:** `src/bank_parser/updater/github_updater.py`. La librería `requests` y `packaging.version`. El reemplazo de archivos lo hace un binario auxiliar `updater.exe` (también construido con PyInstaller) para evitar el "no puedo reemplazar el .exe que está corriendo" de Windows.

---

## 12. Stack tecnológico

| Capa | Librería | Motivo |
|------|----------|--------|
| PDF parsing | **pdfplumber** | Ya validado en `sample.py`; mejor que PyPDF para tablas y posicionamiento. |
| PDF tablas (BBVA) | **pdfplumber.extract_tables** | Para layouts tabulares estrictos. |
| Modelos de datos | **pydantic v2** | Validación + serialización JSON gratis. |
| Excel | **openpyxl** | Estándar para .xlsx; soporta múltiples hojas y formato. |
| GUI | **customtkinter** | Look moderno, simple, fácil de empaquetar. |
| GUI drag-and-drop | **tkinterdnd2** | Drop de archivos al window. |
| HTTP | **requests** | Para auto-update. |
| Versionado | **packaging** | Comparar semver correctamente. |
| Build | **PyInstaller** | Empaquetado a `.exe`. |
| Tests | **pytest** + **pytest-cov** | Tests unitarios y de integración. |
| Lint/format | **ruff** + **black** | Estilo consistente. |
| Pre-commit | **pre-commit** | Hooks automáticos. |
| CI | **GitHub Actions** | Tests en cada push, build en cada tag. |

`pyproject.toml` declara todo y permite `pip install -e .[dev]` para desarrollo.

---

## 13. CI/CD — GitHub Actions

**`.github/workflows/ci.yml`** (en cada push/PR):
- Setup Python 3.12 en Windows
- `pip install -e .[dev]`
- `ruff check .` y `black --check .`
- `pytest --cov=src/bank_parser --cov-report=term-missing`
- Falla si cobertura < 80% en `parsers/` y `validators/`.

**`.github/workflows/release.yml`** (al taggear `v*.*.*`):
- Bumpear `_version.py` automáticamente leyendo el tag.
- Correr tests.
- `pyinstaller build/pyinstaller.spec`.
- Comprimir `dist/BankParser/` a `BankParser-vX.Y.Z-win64.zip`.
- Calcular SHA-256.
- Crear GitHub Release con el zip y el SHA como assets.
- Publicar release notes desde `CHANGELOG.md`.

---

## 14. Roadmap de desarrollo (fases)

### Fase 0 — Bootstrap (0.5 días)
- Inicializar repo: `pyproject.toml`, `.gitignore`, `README.md`, estructura de carpetas, pre-commit, `_version.py = "0.0.1"`.
- CI básico: lint + tests vacíos pasando.

### Fase 1 — Core + 1 banco (1.5 días)
- `schema.py`, `io_layer.py`, `bank_detector.py`, `parsers/base.py`, `parsers/_common.py`.
- Implementar **`parsers/banamex.py`** (ya tienes la base con `sample.py`).
- Tests con `samples/banamex/document_20260425111847.pdf`.
- Validators de cuadre.
- CLI mínima `python -m bank_parser <pdf>` que imprima la tabla a stdout (útil para iterar antes de la GUI).

### Fase 2 — Resto de los parsers (3–4 días, ~0.5–1 día por banco)
- `parsers/banbajio.py` + tests
- `parsers/banregio.py` + tests
- `parsers/banorte.py` + tests
- `parsers/bbva.py` + tests (este es el más complejo por las dobles columnas)
- Para cada banco: agregar un PDF de muestra a `samples/<banco>/` y un golden JSON a `samples/golden/`.

### Fase 3 — Exporters (0.5 días)
- `xlsx_exporter.py` (hojas Movimientos, Resumen, Metadatos, Warnings).
- `json_exporter.py`.
- Soporte para output consolidado por RFC.

### Fase 4 — GUI (2 días)
- Layout con CustomTkinter.
- Drag-and-drop con tkinterdnd2.
- Log en vivo, preview de tabla, exportación.
- Manejo de errores con mensajes en español.

### Fase 5 — Auto-update + packaging (1 día)
- `github_updater.py` + UI banner.
- `pyinstaller.spec` afinado (icono, hidden imports de customtkinter, metadata).
- `release.yml` end-to-end con un tag de prueba `v0.1.0-rc1`.

### Fase 6 — Polish & docs (0.5–1 día)
- `docs/architecture.md`, `docs/adding_a_new_bank.md`, `docs/format_drift.md`.
- README con screenshots y quick-start.
- Release `v1.0.0`.

**Total estimado:** ~9–10 días-persona.

---

## 15. Estrategia de testing

### Unit tests (rápidos)
- `test_bank_detector.py`: cada fingerprint detecta correctamente y rechaza ambigüedades.
- `test_parsers/test_*.py`: cada parser produce exactamente el `Statement` golden esperado a partir del PDF de muestra.
- `test_validators.py`: el cuadre detecta bien errores sintéticos.

### Regression tests (golden)
Para cada PDF en `samples/`, hay un JSON correspondiente en `samples/golden/`. El test:
1. Parsea el PDF → `Statement`.
2. Lo serializa a JSON.
3. Compara byte-por-byte con el golden.
4. Si difiere → falla con un diff legible.

Si el cambio es legítimo (mejora del parser), se regenera el golden con `pytest --regen-golden`.

### Format-drift tests
Un test independiente que toma cada PDF y verifica que los `expected_fingerprints` siguen presentes. Si fallan → alguien cambió el PDF de muestra o subió una versión nueva → revisar.

---

## 16. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Banco cambia formato del PDF | Alta | Alto | Sistema de format-drift en 3 capas (§8); el usuario recibe advertencia clara. |
| `pdfplumber` falla con un PDF escaneado (imagen) | Media | Alto | Detectar `len(extract_text()) < N` y mostrar mensaje "Este PDF parece escaneado, no soportado por ahora". OCR queda fuera del alcance v1. |
| Antivirus bloquea el .exe | Media | Medio | Modo `onedir` (no `onefile`), considerar firma de código en futuro, documentar en README. |
| Auto-update rompe la app | Baja | Alto | Verificación SHA-256, rollback automático si la nueva versión no arranca, mantener copia de la anterior. |
| Decimal vs float en montos | Media | Alto | Usar `Decimal` siempre, nunca `float`. Tests específicos con cantidades problemáticas. |
| Encoding de caracteres especiales (ñ, acentos) | Baja | Bajo | UTF-8 explícito en todo I/O; tests con un PDF que tenga acentos. |
| RFC ausente o ilegible en el PDF | Media | Medio | Si no hay RFC, la columna queda `null` y la consolidación por titular cae a "manual" (selección en GUI). |

---

## 17. Glosario y convenciones

- **Movimiento (Movement):** una transacción individual (un renglón de la tabla del PDF).
- **Statement:** todo lo extraído de un PDF (resumen + lista de movimientos + warnings).
- **Format drift:** cambio en el layout del PDF por parte del banco que rompe el parser.
- **Golden file:** archivo de referencia (JSON serializado del Statement esperado) usado para regression tests.
- **Fingerprint:** string distintivo del PDF que permite identificar al banco emisor.
- **Cuadre:** verificación numérica de que `saldo_inicial + Σabonos − Σcargos = saldo_final`.

### Convenciones de código
- Type hints obligatorios en toda función pública.
- Docstrings en español (público objetivo).
- Mensajes de error y logs **en español**, ya que los usuarios finales son contadores hispanohablantes.
- Identificadores en código en inglés (estándar Python).

---

## 18. Próximos pasos inmediatos

1. **Revisar este plan** y aprobar/ajustar.
2. Crear el repo en GitHub (este folder).
3. Ejecutar la Fase 0 (bootstrap): scaffolding del proyecto + CI básico.
4. Empezar Fase 1 con Banamex (parser que ya tienes parcialmente).
5. Ir agregando bancos uno a uno, priorizando los que más usa la consultoría.

---

*Fin del plan.*
