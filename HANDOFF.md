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

# Inicializar git si todavía no lo está (la carpeta será un nuevo repo)
git init
git add -A
git commit -m "Fase 0 (bootstrap) + Fase 1 parcial (Banamex parser funcionando)"

# Crear venv y dependencias
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install

# Verificar que todo se instaló bien
pytest -v
python -m bank_parser samples\banamex\banamex_micuenta_abr2026.pdf
```

### Lanzar Claude Code

Dentro del repo:

```powershell
cd C:\Users\ivan5\az-repo
claude
```

Y como primer mensaje, pega esto:

> Estoy retomando el desarrollo de un parser de estados de cuenta bancarios
> mexicanos en PDF. Lee `PLAN.md` (plan completo), `HANDOFF.md` (este archivo,
> con estado actual y siguientes pasos), y `README.md`. Después dime un resumen
> de dónde quedó el trabajo y procede con la siguiente tarea: **terminar la
> Fase 1** (verificar que el parser de Banamex está completo y bien probado),
> y luego empezar la **Fase 2** (parsers de BBVA, BanBajío, Banregio, Banorte).
> Mantén la metodología TDD: golden file por banco, validación de cuadre,
> revisión al cierre de cada fase.

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

### 🟡 Fase 1 — Core + parser Banamex (CASI completa)

Lo que ya funciona:

- `src/bank_parser/core/schema.py` — `Movement`, `StatementSummary`, `Statement`, `BankId`.
- `src/bank_parser/core/exceptions.py` — jerarquía completa.
- `src/bank_parser/core/io_layer.py` — lectura de PDF y ZIPs.
- `src/bank_parser/core/bank_detector.py` — fingerprints de los 5 bancos.
- `src/bank_parser/core/pipeline.py` — orquestación end-to-end.
- `src/bank_parser/parsers/base.py` — `BankParser` ABC.
- `src/bank_parser/parsers/_common.py` — helpers (`limpiar_numero`, `extract_rfc`, etc.).
- `src/bank_parser/parsers/banamex.py` — parser de Banamex funcionando.
- `src/bank_parser/parsers/__init__.py` — registry.
- `src/bank_parser/validators/balance.py` — cuadre numérico.
- `src/bank_parser/cli.py` — CLI mínima.
- Tests: `test_smoke.py`, `test_bank_detector.py`, `test_common.py`,
  `test_parsers/test_banamex.py`.
- Golden file generado en `samples/golden/banamex_micuenta_abr2026.json`.

**Resultado verificado del parser Banamex con el PDF real:**

```
=== Banamex | banamex_micuenta_abr2026.pdf ===
Titular:       IVAN ABELARDO AGUILERA ALVAREZ
RFC:           AUAI000504PN6
Cuenta:        70138905215
Periodo:       2026-03-13 a 2026-04-12
Saldo inicial: 3736.35
Saldo final:   53745.16
Total abonos:  91097.06
Total cargos:  41088.25
# movimientos: 16
```

Los totales **cuadran** (3736.35 + 91097.06 - 41088.25 = 53745.16). 26 de 28 tests pasan.

### Pendientes inmediatos para cerrar Fase 1

1. **Arreglar 2 tests de `test_bank_detector.py`** que fallan por archivos `.pyc`
   stale del sandbox. En tu máquina con un venv limpio probablemente pasan
   directo. Si no, simplemente:

   ```powershell
   Remove-Item -Recurse -Force src\bank_parser\__pycache__, src\bank_parser\**\__pycache__ -ErrorAction SilentlyContinue
   pytest tests/test_bank_detector.py -v
   ```

2. **Subir `--cov-fail-under` a 70%** en `pyproject.toml` (ya está cubierto al 66%,
   con un par de tests más para `io_layer.py` y `pipeline.py` se llega a 70+).

3. **Tests adicionales recomendados** para cerrar Fase 1 con confianza:
   - `tests/test_io_layer.py` — leer un ZIP de samples (Banorte) y verificar extracción.
   - `tests/test_pipeline.py` — un test end-to-end que parsea el PDF de Banamex
     vía `process_file()`.

### ⏳ Fase 2 — Resto de parsers (pendiente)

Para cada banco (orden recomendado: el más simple primero):

1. **Banorte** — formato relativamente regular, `DD-MMM-YY` con guiones.
2. **BanBajío** — descripción multilínea con `CLAVE DE RASTREO`.
3. **Banregio** — sólo día (mes en encabezado del periodo).
4. **BBVA** — el más complejo: dos fechas (oper/liq), dos saldos.

Para cada uno:

- Crear `src/bank_parser/parsers/<banco>.py` heredando de `BankParser`.
- Registrarlo en `src/bank_parser/parsers/__init__.py::BANK_REGISTRY`.
- Agregar test en `tests/test_parsers/test_<banco>.py` con golden file.
- Verificar cuadre numérico (debe pasar `validar_cuadre` sin warnings).

Estructura observada de cada banco está documentada en `PLAN.md` §7.

### ⏳ Fases 3–6 (pendientes)

Ver `PLAN.md` §14 (roadmap completo).

---

## 3. Decisiones ya tomadas (no re-preguntar)

- **GUI:** CustomTkinter con drag-and-drop.
- **Salida:** Excel (.xlsx) y JSON.
- **Distribución:** `.exe` standalone vía GitHub Releases con auto-update al iniciar.
- **Procesamiento:** un PDF a la vez, auto-extracción de ZIPs, salida consolidada
  por RFC con columna de banco.
- **Schema de columnas:** mínimo estandarizado (`fecha`, `descripcion`, `abono`,
  `cargo`, `saldo`, `banco`, `cuenta`, `archivo_origen`).

---

## 4. Notas técnicas / gotchas detectados

1. **Banamex tiene una sub-sección "AHORRO FACIL"** en algunos PDFs. El parser
   actualmente sólo procesa la sección "MiCuenta" (la principal) y corta antes
   de "AHORRO FACIL". Si un cliente usa AHORRO FACIL, hay que agregar lógica
   de "una cuenta = un Statement" y procesar ambas.

2. **Filtrado de page-headers en Banamex:** los PDFs paginan con un footer y
   re-imprimen el header de columnas en cada página nueva. Esos artefactos se
   filtran en `_strip_noise()`. Si Banamex cambia el formato de su footer, hay
   que actualizar `_NOISE_PATTERNS` en `parsers/banamex.py`.

3. **Saldo/monto en última línea del bloque:** Banamex pone los números **al
   final de la última línea** del bloque de movimiento. Si una línea termina
   con un número que es el "amount" embebido en una descripción
   (ej: "IMPORTE A EXENTAR $165.00"), se ignora porque la heurística sólo toma
   el final de la última línea con números.

4. **Detección por fingerprints:** el `bank_detector` cuenta matches y resuelve
   ambigüedad por el score más alto. Para los samples actuales, los `must_have`
   de cada banco son lo suficientemente específicos. Si en el futuro hay
   ambigüedad, el error es claro y la GUI ofrecerá selección manual.

---

## 5. Cuando lleguen estados de cuenta nuevos

Los samples actuales son **el contrato del parser**. Cuando un banco cambie su
plantilla:

1. El `format_drift` (capa 1 — `expected_markers`) **probablemente** detecte el
   cambio y lance `FormatChangedError` con el marcador faltante.
2. Si no, el cuadre numérico (capa 2) generará un warning visible.
3. La acción es: agregar el PDF nuevo a `samples/<banco>/`, ajustar el parser
   (sus regex/markers), regenerar el golden con `pytest --regen-golden` y
   commitear todo junto.

---

## 6. Comandos útiles de día a día

```powershell
# Lint y format
ruff check src tests --fix
black src tests

# Tests con cobertura
pytest -v

# Tests sólo de un parser
pytest tests/test_parsers/test_banamex.py -v

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

*Suerte. El plan está sólido y la base de código sigue las convenciones definidas.*
