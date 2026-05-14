# Bank Parser — Estados de Cuenta Bancarios MX

Convierte PDFs de estados de cuenta de los principales bancos mexicanos en
tablas estandarizadas de movimientos (`.xlsx` y `.json`).

| Banco | Producto soportado |
|---|---|
| **Banamex** (Citibanamex) | MiCuenta, Cuenta Priority |
| **BBVA México** | Cash Management M.N., Maestra PYME |
| **BanBajío** | Cuenta Conecta |
| **Banregio** | Cuenta Naranja Negocios |
| **Banorte** | Enlace Negocios |

---

## Instalación rápida (usuario final)

1. Descarga el archivo `BankParser-vX.Y.Z-win64.zip` de la sección
   [Releases](https://github.com/Yvsvan/az-repo/releases).
2. Descomprime en cualquier carpeta.
3. Ejecuta `BankParser.exe`.

La app comprueba actualizaciones automáticamente al iniciar y muestra un
aviso si hay una versión nueva disponible.

> **Requisito del sistema:** Windows 10/11 x64.
> No se necesita instalar Python ni ninguna otra dependencia.

---

## Uso — Interfaz gráfica

```
┌─────────────────────────────────────────────────────────────────┐
│  🏦  Parser de Estados de Cuenta Bancarios          v0.1.0      │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │   📄  Suelta tus PDFs o ZIPs aquí                           │ │
│ │       (o haz clic para seleccionar archivos)                │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Archivos cargados:                               [Limpiar todo]│
│  ✓  bbva_feb2026.pdf      BBVA     RFC: CEL810729LY8  86 movs  │
│  ⚠  banregio_ene2026.pdf  Banregio RFC: CEL810729LY8 167 movs  │
│  ✗  raro.pdf              Error: banco no detectado             │
│                                                                 │
│  Log de progreso:                                               │
│  [10:42:01] ✓ bbva_feb2026.pdf → BBVA | RFC: CEL… | 86 movs   │
│  [10:42:02] ⚠ banregio_ene2026.pdf: 2 advertencias             │
│                                                                 │
│  Salida: C:\Users\ivan\Desktop               [📁 Cambiar]       │
│  [▶ Procesar]    [📊 Exportar .xlsx]    [{ } Exportar .json]   │
└─────────────────────────────────────────────────────────────────┘
```

**Flujo de trabajo:**

1. Arrastra uno o varios PDFs/ZIPs a la ventana (o usa el botón Seleccionar).
2. Haz clic en **▶ Procesar**. El log muestra el progreso en tiempo real.
3. Cuando todos los archivos muestren `✓` (o `⚠` con advertencias aceptables),
   haz clic en **📊 Exportar .xlsx** o **{ } Exportar .json**.
4. El archivo se guarda en la carpeta de salida configurada
   (por defecto, el Escritorio).

**Íconos de estado:**

| Ícono | Significado |
|---|---|
| `○` | Pendiente de procesar |
| `⟳` | Procesando... |
| `✓` | OK — cuadre correcto |
| `⚠` | Procesado con advertencias (ver log) |
| `✗` | Error — no se pudo procesar |

---

## Uso — Línea de comandos (CLI)

```bash
# Parsear un PDF e imprimir resumen en consola
python -m bank_parser ruta/al/estado.pdf

# Exportar a Excel
python -m bank_parser ruta/al/estado.pdf -o movimientos.xlsx

# Exportar a JSON
python -m bank_parser ruta/al/estado.pdf -o movimientos.json

# Los ZIPs también funcionan directamente
python -m bank_parser estados_banorte.zip -o banorte.xlsx
```

---

## Uso — API Python

```python
from bank_parser import parse_pdf, BankId

statements = parse_pdf("estado_bbva_feb2026.pdf")   # list[Statement]

for stmt in statements:
    s = stmt.summary
    print(f"{s.banco.display_name} | {s.rfc} | {len(stmt.movements)} movimientos")
    print(f"Saldo inicial: {s.saldo_inicial}  →  Saldo final: {s.saldo_final}")
    if stmt.warnings:
        print("Advertencias:", stmt.warnings)

# Exportar programáticamente
from bank_parser.exporters import export_to_xlsx, export_to_json

export_to_xlsx(statements, "movimientos.xlsx")
export_to_json(statements, "movimientos.json")
```

### Columnas del Excel / campos de `Movement`

| Campo | Tipo | Descripción |
|---|---|---|
| `fecha` | `date` | Fecha de la transacción |
| `descripcion` | `str` | Texto del concepto |
| `abono` | `Decimal` | Monto depositado (`0` si es cargo) |
| `cargo` | `Decimal` | Monto retirado (`0` si es abono) |
| `saldo` | `Decimal` | Saldo después del movimiento |
| `banco` | `BankId` | Banco emisor |
| `cuenta` | `str` | Número de cuenta |
| `archivo_origen` | `str` | Nombre del PDF de origen |

---

## Instalación para desarrollo

Requiere Python 3.10+.

```bash
git clone https://github.com/Yvsvan/az-repo.git
cd az-repo
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -e ".[dev]"
pre-commit install
pytest
```

### Comandos del día a día

```bash
# Tests con cobertura
pytest -v

# Solo los tests de un parser
pytest tests/test_parsers/test_bbva.py -v

# Regenerar golden files después de un cambio legítimo en el parser
pytest --regen-golden

# Lint y formato
ruff check src tests --fix
black src tests

# Build del .exe
pyinstaller build/pyinstaller.spec --noconfirm
# → dist/BankParser/BankParser.exe
```

---

## Arquitectura resumida

```
PDF/ZIP
  └─ io_layer          →  extrae texto y bytes del PDF
       └─ bank_detector →  identifica el banco por fingerprints
            └─ parsers/<banco>.py  →  extrae movimientos con regex
                 └─ validators     →  cuadre numérico + format-drift
                      └─ exporters →  xlsx / json
```

Para la arquitectura completa ver [`docs/architecture.md`](docs/architecture.md).

### Agregar un nuevo banco

Ver la guía detallada en [`docs/adding_a_new_bank.md`](docs/adding_a_new_bank.md).
Resumen en 6 pasos:

1. `src/bank_parser/core/schema.py` → añadir `BankId`.
2. `src/bank_parser/core/bank_detector.py` → añadir fingerprints.
3. `src/bank_parser/parsers/<nuevo>.py` → implementar `BankParser`.
4. `src/bank_parser/parsers/__init__.py` → registrar en `BANK_REGISTRY`.
5. `samples/<nuevo>/` + `samples/golden/` → PDF de muestra y golden JSON.
6. `tests/test_parsers/test_<nuevo>.py` → tests de regresión.

---

## Detección de cambios de formato

Cuando un banco actualiza la plantilla de su PDF el parser puede fallar.
El sistema tiene tres capas de defensa:

1. **`expected_markers`** — si falta un encabezado estructural → `FormatChangedError`.
2. **Cuadre numérico** — si `saldo_inicial + Σabonos − Σcargos ≠ saldo_final` → warning.
3. **Golden files en CI** — los PDFs de muestra están bajo control de versiones;
   cualquier cambio de output dispara un fallo en la suite.

Ver [`docs/format_drift.md`](docs/format_drift.md) para más detalles.

---

## Licencia

MIT — ver [LICENSE](LICENSE).
