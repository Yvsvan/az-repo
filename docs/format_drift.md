# Detección de cambios de formato (Format Drift)

Cuando un banco rediseña la plantilla de su estado de cuenta, el parser puede
empezar a fallar silenciosamente o a producir datos incorrectos. Este documento
describe las tres capas de defensa del sistema y cómo actuar cuando se detecta
un drift.

---

## Qué es el format drift

Un banco puede cambiar:

- La posición o etiqueta de un campo de cabecera (RFC, titular, periodo...).
- El ancho, separador o número de columnas en la tabla de movimientos.
- El orden de las secciones dentro del PDF.
- La codificación interna del PDF (afecta a lo que `pdfplumber` extrae).

El sistema detecta estos cambios en tres momentos distintos.

---

## Capa 1 — `expected_markers` (detección temprana)

Cada parser declara un conjunto de strings estructurales que **deben** estar
presentes en el texto del PDF:

```python
class BanamexParser(BankParser):
    expected_markers = [
        "Citibanamex",
        "Estado de Cuenta",
        "MOVIMIENTOS DEL PERIODO",
    ]
```

El método `_assert_markers(text)` de la clase base verifica su presencia antes
de cualquier extracción. Si falta uno:

```
bank_parser.core.exceptions.FormatChangedError:
  [BANAMEX] Marcador ausente: 'MOVIMIENTOS DEL PERIODO'
  Posiblemente el banco cambió el formato del PDF.
```

**Cuándo agregar markers:**
- Añade un marker cuando encuentres un string que sea un "ancla" para tu regex
  más importante.
- No añadas strings demasiado genéricos (`"FECHA"`, `"SALDO"`).
- Evita strings con espacios variables o que cambian con el locale del PDF.

---

## Capa 2 — Cuadre numérico (detección post-parseo)

Después de parsear todos los movimientos, `validators/balance.py` comprueba:

```
saldo_inicial + Σabonos − Σcargos ≈ saldo_final        (tolerancia 0.01 MXN)
Σabonos_calculado ≈ total_abonos_del_PDF               (tolerancia 0.01 MXN)
Σcargos_calculado ≈ total_cargos_del_PDF               (tolerancia 0.01 MXN)
```

Si alguna condición falla, el `Statement` se devuelve con warnings:

```python
stmt.warnings = [
    "Cuadre: saldo_inicial(10,000.00) + abonos(5,000.00) - cargos(3,000.00) "
    "= 12,000.00 ≠ saldo_final(12,001.50) — diferencia: 1.50"
]
```

El proceso **no aborta** — el output se entrega con la advertencia para que el
usuario pueda decidir.

### Casos conocidos de descuadre legítimo

| Banco | Causa |
|---|---|
| Banregio | Comisiones (`~440.80 MXN`) que aparecen en el resumen pero no en el detalle de movimientos del PDF. |

Estos casos están documentados en los tests:

```python
def test_cuadre_warnings_conocidos(self):
    stmts = parse_pdf(SAMPLE)
    # La diferencia es la comisión que el PDF no desglosa
    assert any("diferencia" in w for w in stmts[0].warnings)
```

---

## Capa 3 — Golden files en CI (detección de regresión)

Cada parser tiene un golden file: una salida JSON conocida-buena. La suite de
tests compara la salida actual contra el golden:

```python
def test_golden_regression(self, regen_golden: bool):
    stmts = parse_pdf(SAMPLE)
    actual = json.loads(stmts[0].model_dump_json())

    if regen_golden:
        GOLDEN.write_text(json.dumps(actual, ...), ...)
        pytest.skip("Golden regenerado")

    expected = json.loads(GOLDEN.read_text(...))
    assert actual == expected      # falla si cualquier campo cambia
```

Si el banco cambia su formato, el parser deja de extraer algún campo
correctamente y el golden test falla en CI antes de que el bug llegue a
producción.

---

## Flujo de acción ante un drift detectado

### Escenario A — `FormatChangedError` en producción

```
[ERROR] banamex_abr2026.pdf → FormatChangedError: Marcador ausente: 'MOVIMIENTOS DEL PERIODO'
```

1. Descarga el PDF problemático.
2. Extrae el texto con pdfplumber:
   ```python
   import pdfplumber
   with pdfplumber.open("banamex_abr2026.pdf") as pdf:
       for p in pdf.pages:
           print(p.extract_text())
   ```
3. Busca el nuevo texto del marcador (e.g., `"DETALLE DE MOVIMIENTOS"`).
4. Actualiza `expected_markers` y los regex del parser.
5. Regenera el golden con el nuevo PDF de muestra:
   ```bash
   pytest tests/test_parsers/test_banamex.py --regen-golden
   ```
6. Corre la suite completa y abre un PR.

### Escenario B — Cuadre incorrecto (diferencia grande)

```
[WARN] saldo_inicial + abonos - cargos = 45,230.00 ≠ saldo_final(45,100.00) — diferencia: 130.00
```

1. Verifica manualmente el PDF: ¿hay movimientos que el regex no captura?
2. Ajusta el patrón de extracción de movimientos.
3. Si la diferencia es intencional (comisión no desglosada), documenta el caso
   en el test con `test_cuadre_warnings_conocidos`.

### Escenario C — Golden test falla pero el código no cambió

El banco cambió su PDF. Verifica el diff:

```bash
pytest tests/test_parsers/test_banamex.py -v 2>&1 | grep "AssertionError"
```

Sigue el flujo del Escenario A desde el paso 2.

---

## Agregar un nuevo `expected_marker`

Si encuentras un formato nuevo que tu regex no cubre:

1. Añade el string a `expected_markers` para que futuros PDFs inválidos fallen
   rápido.
2. Si el string puede variar entre versiones del PDF (e.g., mayúsculas vs.
   mixto), usa `_find_opt` en lugar de marcarlo obligatorio.

---

## Configuración de tolerancia

La tolerancia de 0.01 MXN está definida en `validators/balance.py`:

```python
_TOLERANCIA = Decimal("0.01")
```

No se recomienda aumentarla. Si la diferencia es sistemáticamente mayor,
el problema es del parser, no de la tolerancia.
