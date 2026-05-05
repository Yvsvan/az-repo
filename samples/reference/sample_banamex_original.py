import re
import pandas as pd
import pdfplumber

def limpiar_numero(num_str):
    return float(num_str.replace(",", ""))

def parsear_estado_cuenta(ruta_pdf):
    # Leer PDF
    texto = ""
    with pdfplumber.open(ruta_pdf) as pdf:
        for pagina in pdf.pages:
            texto += pagina.extract_text() + "\n"

    # -------- SALDO INICIAL --------
    regex_saldo_inicial = r"(\d{2}\s+[A-Z]{3})\s+SALDO\s+ANTERIOR\s+([\d,]+\.\d{2})"

    match_inicial = re.search(regex_saldo_inicial, texto, re.MULTILINE)

    if not match_inicial:
        raise ValueError("No se encontró saldo inicial")

    saldo_inicial = limpiar_numero(match_inicial.group(2))

    # 1. Cortar desde saldo inicial
    texto_movimientos = texto[match_inicial.end():]

    # 2. Cortar hasta "Estado de Cuenta"
    fin_match = re.search(r"Estado de Cuenta", texto_movimientos, re.IGNORECASE)
    if fin_match:
        texto_movimientos = texto_movimientos[:fin_match.start()]

    # -------- MOVIMIENTOS --------
    regex_movimientos = r"(\d{2}\s+[A-Z]{3})([\s\S]*?)(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d{1,3}(?:,\d{3})*\.\d{2})"
    matches = re.findall(regex_movimientos, texto_movimientos, re.MULTILINE)

    data = []
    saldo_prev = saldo_inicial

    for fecha, descripcion, monto_str, saldo_str in matches:
        monto = limpiar_numero(monto_str)
        saldo = limpiar_numero(saldo_str)

        # Determinar tipo
        if saldo > saldo_prev:
            abono = monto
            retiro = 0
        else:
            abono = 0
            retiro = monto

        data.append({
            "fecha": fecha,
            "descripcion": descripcion.strip().replace("\n", " "),
            "abono": abono,
            "retiro": retiro,
            "saldo": saldo
        })

        saldo_prev = saldo

    df = pd.DataFrame(data)

    return saldo_inicial, df


# -------- USO --------
ruta = r"C:\Users\ivan5\Downloads\santander.pdf"

saldo_inicial, df = parsear_estado_cuenta(ruta)

print("Saldo inicial:", saldo_inicial)
print(df.head())

df.to_csv(r"C:\Users\ivan5\Downloads\test.csv", index=False)