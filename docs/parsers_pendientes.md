# Parsers Pendientes

Estos archivos fueron identificados en el lote de enero 2024 pero se pospuso
su implementación. Cada uno tiene un formato distinto al de los extractos de
cuenta corriente ya soportados.

| Archivo | Tipo | Razón de omisión |
|---------|------|-----------------|
| PDF ENE 2024 BBVA CREDT 2313.pdf / 4057.pdf | Tarjeta de crédito BBVA | Formato diferente al de cuenta de cheques; requiere parser dedicado |
| PDF ENE 2024 BBVA FON INVERSION.pdf | Fondo de inversión BBVA | Sin movimientos estándar de cargo/abono; reporte de rendimientos |
| PDF ENE 2024 BANAMEX INV 9546946.pdf | Portafolio de inversión Banamex | Estado de cuenta de valores, no de efectivo |
| PDF ENE 2024 BANAMEX TARJ CTA 0095.pdf | Tarjeta de crédito Banamex | Formato de estado de cuenta de crédito |
| PDF ENE 2024 BANORTE CREDT SIMP INC.pdf | Crédito simple Banorte | Estado de crédito con solo ~2 movimientos; formato de préstamo |
| PDF ENE 2024 BAJIO CREDT EMPRESARIAL.pdf | Línea de crédito Banbajío | Formato complejo de crédito empresarial |

## Notas de implementación

- **Tarjetas de crédito** (BBVA CREDT, BANAMEX TARJ): el encabezado y las
  columnas difieren de los extractos de cheques. Hay que definir un `BankId`
  nuevo por cada producto y un parser que extraiga `fecha`, `descripcion`,
  `cargo`, `abono` del estado de tarjeta.

- **Fondos / Portafolios** (BBVA FON INVERSION, BANAMEX INV): no tienen
  movimientos de efectivo cotidianos; evaluar si se modelan como `Statement`
  con tipo diferente o si se excluyen del pipeline principal.

- **Créditos** (BANORTE CREDT, BAJIO CREDT EMPRESARIAL): formato de estado de
  préstamo/línea. Pocos movimientos (disposiciones y pagos). Revisar si el
  esquema `Movement` actual es suficiente o si se necesita un campo `tipo`.

## Cómo agregar un parser nuevo

Ver [adding_a_new_bank.md](adding_a_new_bank.md) para el paso a paso completo.
