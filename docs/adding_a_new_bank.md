# Guía: Agregar un nuevo banco

Esta guía describe el proceso completo para añadir soporte a un banco nuevo,
desde el fingerprint de detección hasta los tests de regresión.

---

## Paso 1 — Añadir el `BankId` en `core/schema.py`

```python
# src/bank_parser/core/schema.py
class BankId(str, Enum):
    BANAMEX  = "banamex"
    BBVA     = "bbva"
    BANBAJIO = "banbajio"
    BANREGIO = "banregio"
    BANORTE  = "banorte"
    MIBANK   = "mibank"          # ← nuevo

    @property
    def display_name(self) -> str:
        _NAMES = {
            "banamex":  "Banamex (Citibanamex)",
            "bbva":     "BBVA México",
            "banbajio": "BanBajío",
            "banregio": "Banregio",
            "banorte":  "Banorte",
            "mibank":   "Mi Banco",              # ← nuevo
        }
        return _NAMES[self.value]
```

Solo un valor y una entrada en `_NAMES`. No hay más cambios en este archivo.

---

## Paso 2 — Añadir fingerprints en `core/bank_detector.py`

El detector usa un esquema de puntuación:

- **`must_have`** — strings que *deben* aparecer en el texto. Si falta uno, el
  score es 0.
- **`boost`** — strings opcionales que suman puntos adicionales.

```python
# src/bank_parser/core/bank_detector.py
_FINGERPRINTS: dict[BankId, _Fingerprint] = {
    ...
    BankId.MIBANK: _Fingerprint(
        must_have=["MI BANCO", "ESTADO DE CUENTA"],
        boost=["RFC:", "CUENTA CORRIENTE", "SALDO FINAL"],
    ),
}
```

### Cómo elegir buenos fingerprints

1. Abre 2-3 PDFs del banco en un editor de texto o con `pdfplumber`:
   ```python
   import pdfplumber
   with pdfplumber.open("estado.pdf") as pdf:
       print(pdf.pages[0].extract_text())
   ```
2. Busca strings únicos que **no aparezcan** en PDFs de otros bancos.
3. Ponlos en `must_have`. Añade strings adicionales en `boost` para desambiguar.

### Verificar que no hay colisiones

```bash
pytest tests/test_bank_detector.py -v
```

El test `test_no_cross_detection` carga el texto de cada PDF de muestra y
verifica que sólo se detecta un banco.

---

## Paso 3 — Crear `parsers/mibank.py`

Crea el archivo heredando de `BankParser`:

```python
# src/bank_parser/parsers/mibank.py
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from bank_parser.core.schema import BankId, Movement, Statement, StatementSummary
from bank_parser.parsers.base import BankParser


class MiBankParser(BankParser):
    bank_id = BankId.MIBANK

    # Strings que deben existir en el texto; si alguno falta → FormatChangedError
    expected_markers = [
        "MI BANCO",
        "ESTADO DE CUENTA",
        "MOVIMIENTOS",
    ]

    def parse(self, text: str, *, pdf_bytes: bytes, archivo_origen: str) -> Statement:
        self._assert_markers(text)        # lanza FormatChangedError si falta algún marker

        summary  = self._parse_summary(text, archivo_origen)
        movements = self._parse_movements(text, summary, archivo_origen)

        return Statement(summary=summary, movements=movements)

    # ------------------------------------------------------------------
    def _parse_summary(self, text: str, archivo_origen: str) -> StatementSummary:
        # Extrae RFC, titular, cuenta, periodo, saldos con regex
        rfc     = self._find(r"RFC[:\s]+([A-Z0-9]{12,13})", text)
        titular = self._find(r"TITULAR[:\s]+(.+)", text)
        cuenta  = self._find(r"CUENTA[:\s]+([\d\-]+)", text)

        fecha_inicio = self._parse_date(self._find(r"DEL\s+(\d{2}/\d{2}/\d{4})", text))
        fecha_fin    = self._parse_date(self._find(r"AL\s+(\d{2}/\d{2}/\d{4})", text))

        saldo_inicial = Decimal(self._find(r"SALDO ANTERIOR[:\s]+([\d,]+\.\d{2})", text).replace(",", ""))
        saldo_final   = Decimal(self._find(r"SALDO FINAL[:\s]+([\d,]+\.\d{2})", text).replace(",", ""))
        total_abonos  = Decimal(self._find(r"TOTAL ABONOS[:\s]+([\d,]+\.\d{2})", text).replace(",", ""))
        total_cargos  = Decimal(self._find(r"TOTAL CARGOS[:\s]+([\d,]+\.\d{2})", text).replace(",", ""))

        return StatementSummary(
            banco=BankId.MIBANK,
            titular=titular,
            rfc=rfc,
            cuenta=cuenta,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            saldo_inicial=saldo_inicial,
            saldo_final=saldo_final,
            total_abonos=total_abonos,
            total_cargos=total_cargos,
            archivo_origen=archivo_origen,
        )

    def _parse_movements(
        self,
        text: str,
        summary: StatementSummary,
        archivo_origen: str,
    ) -> list[Movement]:
        # Adapta el patrón al formato real del banco
        _ROW = re.compile(
            r"(?P<day>\d{2})\s+"
            r"(?P<desc>.+?)\s+"
            r"(?P<abono>[\d,]+\.\d{2})?\s*"
            r"(?P<cargo>[\d,]+\.\d{2})?\s*"
            r"(?P<saldo>[\d,]+\.\d{2})"
        )
        year  = summary.fecha_inicio.year
        month = summary.fecha_inicio.month
        movs: list[Movement] = []

        for m in _ROW.finditer(text):
            abono = Decimal(m.group("abono").replace(",", "")) if m.group("abono") else Decimal("0")
            cargo = Decimal(m.group("cargo").replace(",", "")) if m.group("cargo") else Decimal("0")
            saldo = Decimal(m.group("saldo").replace(",", ""))

            movs.append(Movement(
                fecha=date(year, month, int(m.group("day"))),
                descripcion=m.group("desc").strip(),
                abono=abono,
                cargo=cargo,
                saldo=saldo,
                banco=BankId.MIBANK,
                cuenta=summary.cuenta,
                archivo_origen=archivo_origen,
            ))

        return movs
```

### Métodos heredados de `BankParser`

| Método | Qué hace |
|---|---|
| `_assert_markers(text)` | Lanza `FormatChangedError` si falta algún `expected_markers` |
| `_find(pattern, text, group=1)` | Busca con `re.search`; lanza `ParseError` si no encuentra |
| `_find_opt(pattern, text, group=1)` | Como `_find` pero devuelve `None` si no encuentra |
| `_parse_date(s, fmts)` | Intenta los formatos de fecha dados; lanza `ParseError` si ninguno aplica |

Para PDFs complejos (columnas alineadas por coordenada X como BBVA) puedes
acceder a `pdf_bytes`:

```python
import pdfplumber, io

with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
    for page in pdf.pages:
        words = page.extract_words(x_tolerance=3)
        ...
```

---

## Paso 4 — Registrar el parser en `parsers/__init__.py`

```python
# src/bank_parser/parsers/__init__.py
from bank_parser.parsers.banamex  import BanamexParser
from bank_parser.parsers.bbva     import BBVAParser
from bank_parser.parsers.banbajio import BanBajioParser
from bank_parser.parsers.banregio import BanregioParser
from bank_parser.parsers.banorte  import BanorteParser
from bank_parser.parsers.mibank   import MiBankParser   # ← nuevo

BANK_REGISTRY: dict[BankId, type[BankParser]] = {
    BankId.BANAMEX:  BanamexParser,
    BankId.BBVA:     BBVAParser,
    BankId.BANBAJIO: BanBajioParser,
    BankId.BANREGIO: BanregioParser,
    BankId.BANORTE:  BanorteParser,
    BankId.MIBANK:   MiBankParser,    # ← nuevo
}
```

El pipeline usa `BANK_REGISTRY` para instanciar el parser correcto. No hay
más cambios en el pipeline.

---

## Paso 5 — Añadir un PDF de muestra y el golden file

```
samples/
  mibank/
    mibank_cuenta_ene2026.pdf   ← PDF real del banco (no se sube información sensible)
  golden/
    mibank_cuenta_ene2026.json  ← salida esperada
```

### Generar el golden file

```bash
# 1. Parsea el PDF manualmente para ver el resultado:
python -c "
import bank_parser, json
stmts = bank_parser.parse_pdf('samples/mibank/mibank_cuenta_ene2026.pdf')
print(stmts[0].model_dump_json(indent=2))
"

# 2. Si el resultado es correcto, genera el golden con la flag:
pytest tests/test_parsers/test_mibank.py --regen-golden
```

**Qué incluir en el PDF de muestra:**
- Datos reales del banco, pero con RFC/titular ficticios o de una empresa
  de pruebas.
- Idealmente un mes con movimientos variados: abonos, cargos, comisiones.

---

## Paso 6 — Crear `tests/test_parsers/test_mibank.py`

```python
# tests/test_parsers/test_mibank.py
from pathlib import Path
import pytest
from bank_parser import parse_pdf, BankId


SAMPLE = Path("samples/mibank/mibank_cuenta_ene2026.pdf")
GOLDEN = Path("samples/golden/mibank_cuenta_ene2026.json")


@pytest.mark.skipif(not SAMPLE.exists(), reason="PDF de muestra no disponible")
class TestMiBankParser:

    def test_banco_detectado(self):
        stmts = parse_pdf(SAMPLE)
        assert stmts[0].summary.banco == BankId.MIBANK

    def test_movimientos_no_vacios(self):
        stmts = parse_pdf(SAMPLE)
        assert len(stmts[0].movements) > 0

    def test_saldo_inicial_positivo(self):
        stmts = parse_pdf(SAMPLE)
        assert stmts[0].summary.saldo_inicial >= 0

    def test_golden_regression(self, regen_golden: bool):
        """Compara salida actual contra el golden file."""
        import json
        stmts = parse_pdf(SAMPLE)
        actual = json.loads(stmts[0].model_dump_json())

        if regen_golden:
            GOLDEN.write_text(
                json.dumps(actual, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            pytest.skip("Golden regenerado")

        expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert actual == expected
```

El fixture `regen_golden` y la opción `--regen-golden` ya están definidos en
`tests/conftest.py`.

---

## Checklist de revisión

Antes de hacer merge, verifica:

- [ ] `BankId.MIBANK` añadido con `display_name` correcto.
- [ ] Fingerprints en `bank_detector.py` pasan `test_no_cross_detection`.
- [ ] Parser arroja `FormatChangedError` si se le pasa un PDF de otro banco.
- [ ] `BANK_REGISTRY` actualizado.
- [ ] PDF de muestra en `samples/mibank/`.
- [ ] Golden file en `samples/golden/`.
- [ ] Tests de regresión en `tests/test_parsers/test_mibank.py`.
- [ ] `pytest` completo pasa (≥ 82 % cobertura).
- [ ] `ruff check src tests` y `black src tests` sin errores.
