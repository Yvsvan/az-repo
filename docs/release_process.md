# Proceso de Release

Este documento describe cómo publicar una nueva versión del proyecto, desde
preparar el changelog hasta el `.exe` final publicado en GitHub Releases.

---

## Precondiciones

- Estás en la rama `main` con todos los cambios listos.
- `pytest` pasa al 100 % (o con los warnings esperados documentados).
- `ruff check src tests` y `black src tests` sin errores.
- Tienes permisos de `push` al repositorio.

---

## Paso 1 — Actualizar la versión

La versión vive en **un solo lugar**:

```
src/bank_parser/_version.py
```

```python
__version__ = "0.2.0"   # ← cambia aquí
```

El workflow de CI (`release.yml`) parcheará automáticamente `build/version_info.txt`
al momento del build.

---

## Paso 2 — Actualizar `CHANGELOG.md`

Añade una sección nueva **al principio** del archivo:

```markdown
## [0.2.0] — 2026-06-01

### Added
- Soporte para Banco X (parser + tests de regresión).
- CLI: flag `--quiet` para suprimir el log de progreso.

### Fixed
- Banregio: fechas de diciembre se asignaban incorrectamente al mes siguiente.

### Changed
- BBVA: ahora se detecta el encabezado también en PDFs de 2 páginas.
```

Categorías disponibles: `Added`, `Fixed`, `Changed`, `Removed`, `Security`.

---

## Paso 3 — Commit y tag

```bash
git add src/bank_parser/_version.py CHANGELOG.md
git commit -m "chore: bump version to 0.2.0"

git tag v0.2.0
git push origin main --tags
```

El push del tag dispara el workflow `.github/workflows/release.yml`.

---

## Paso 4 — El workflow de CI

El workflow hace automáticamente:

1. **Sincroniza la versión** — parchea `build/version_info.txt` con el número
   del tag.
2. **Instala dependencias** — `pip install -e ".[dev]"` + `pip install pyinstaller`.
3. **Build con PyInstaller** — `pyinstaller build/pyinstaller.spec --noconfirm`.
   Genera `dist/BankParser/` (modo onedir, ~80 MB).
4. **Comprime** — `BankParser-v0.2.0-win64.zip`.
5. **Calcula SHA-256** — `BankParser-v0.2.0-win64.zip.sha256`.
6. **Publica el Release** — sube el `.zip` y el `.sha256` como assets;
   usa el texto de `CHANGELOG.md` como cuerpo del release.

---

## Paso 5 — Verificar el Release en GitHub

1. Ve a la sección **Releases** del repositorio.
2. Confirma que el `.zip` y el `.sha256` están adjuntos.
3. Descarga el `.zip`, descomprime y ejecuta `BankParser.exe` en una
   máquina limpia (sin Python instalado).
4. Verifica que la app muestra la versión correcta en el título de la ventana.

---

## Hotfix (patch release)

Si se encuentra un bug crítico en una versión publicada:

```bash
# Desde main (o desde un branch de hotfix si main ya tiene cambios):
git checkout -b hotfix/0.2.1

# ... corrige el bug y sus tests ...

# Actualiza _version.py → "0.2.1"
# Añade entrada en CHANGELOG.md

git add -A
git commit -m "fix: descripción del hotfix"
git checkout main
git merge hotfix/0.2.1 --no-ff
git tag v0.2.1
git push origin main --tags
git branch -d hotfix/0.2.1
```

---

## Versionado semántico

Este proyecto usa **SemVer** (`MAYOR.MENOR.PATCH`):

| Tipo de cambio | Incrementar |
|---|---|
| Nuevas funcionalidades sin breaking changes | `MENOR` |
| Corrección de bugs | `PATCH` |
| Cambio en la API pública o ruptura de compatibilidad | `MAYOR` |

Mientras estemos en `0.x.y`, cualquier cambio puede ser breaking (la API
no está estabilizada). A partir de `1.0.0` se aplica SemVer estricto.

---

## Verificar SHA-256 manualmente

```bash
# Windows PowerShell:
Get-FileHash BankParser-v0.2.0-win64.zip -Algorithm SHA256

# Linux / macOS:
sha256sum BankParser-v0.2.0-win64.zip

# Compara contra el contenido de BankParser-v0.2.0-win64.zip.sha256
```
