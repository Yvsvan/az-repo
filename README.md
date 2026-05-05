# bank-parser

Parser de estados de cuenta bancarios mexicanos (PDF) → tabla estandarizada de movimientos.

Bancos soportados (v0.x):

- Banamex (Citibanamex / MiCuenta)
- BBVA México (Cash Management)
- BanBajío (Cuenta Conecta)
- Banregio (Cuenta Naranja Negocios)
- Banorte (Enlace Negocios)

## Instalación (usuario final)

Descarga el `.zip` más reciente desde [Releases](https://github.com/ivan-aguilera/az-repo/releases) y descomprímelo. Ejecuta `BankParser.exe`.

La app verifica automáticamente si hay actualizaciones al iniciar.

## Instalación (desarrollo)

Requiere Python 3.11+ y, en Windows, [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).

```bash
git clone https://github.com/ivan-aguilera/az-repo.git
cd az-repo
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
pre-commit install
pytest
```

## Uso rápido

GUI (default):

```bash
python -m bank_parser
```

CLI (útil para scripts):

```bash
python -m bank_parser samples/banamex/banamex_micuenta_abr2026.pdf -o out/movimientos.xlsx
```

## Arquitectura

Ver [`PLAN.md`](PLAN.md) para el plan de desarrollo completo y [`docs/architecture.md`](docs/architecture.md) para detalles técnicos.

Resumen:

```
PDF → io_layer → bank_detector → parsers/<banco>.py → schema (pydantic)
    → validators (cuadre, format-drift) → exporters (xlsx, json)
```

## Cómo agregar soporte para un nuevo banco

Ver [`docs/adding_a_new_bank.md`](docs/adding_a_new_bank.md). Resumen:

1. Crear `src/bank_parser/parsers/<nuevo>.py` que herede de `BankParser`.
2. Agregar el `BankId` en `core/schema.py`.
3. Registrar el parser en `parsers/__init__.py`.
4. Agregar fingerprints en `core/bank_detector.py`.
5. Agregar PDF de muestra a `samples/<nuevo>/` y golden file a `samples/golden/`.
6. Escribir tests en `tests/test_parsers/test_<nuevo>.py`.

## Licencia

MIT — ver [LICENSE](LICENSE).
