"""
Parser del resumen de tarjeta de crédito de BBVA (Visa y Mastercard).

Es determinista a propósito: no hay LLM en ningún paso. El resumen trae sus
propios totales, y el parser solo devuelve algo si lo que leyó los reproduce al
centavo:

  saldo anterior + pagos y ajustes + consumos + impuestos == saldo actual

por moneda, y la suma de los consumos de cada titular == su TOTAL CONSUMOS. Si
algo no cierra, o aparece una línea con importe que no se sabe leer, se rechaza
el resumen entero (`ResumenInvalido`). Un cambio de formato del banco se nota
así, en vez de cargar datos a medias.

La moneda de cada importe sale de la COLUMNA donde está impreso (PESOS o
DÓLARES), no del texto: los consumos en dólares repiten el monto dentro de la
descripción ("ANTHROPIC* CLAUDE SUB USD 20,00"), y ese número no es un importe.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pdfplumber

MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
_FECHA_RE = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{2})$")
_IMPORTE_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$")
_CUPON_RE = re.compile(r"^\d{6}$")
_CUOTA_RE = re.compile(r"\bC\.(\d{2})/(\d{2})\b")

# Tolerancia (en puntos PDF) entre el borde derecho de un importe y el de su
# encabezado de columna. Los importes están alineados a la derecha.
_TOL_COLUMNA = 8.0
# Dos palabras están en la misma línea si su "top" difiere menos que esto.
_TOL_LINEA = 2.5


class ResumenInvalido(Exception):
    """El PDF no se pudo leer con certeza. No se carga nada."""


@dataclass(frozen=True)
class Palabra:
    texto: str
    x1: float  # borde derecho


@dataclass(frozen=True)
class LineaPdf:
    pagina: int
    palabras: tuple[Palabra, ...]

    @property
    def texto(self) -> str:
        return " ".join(p.texto for p in self.palabras)


@dataclass(frozen=True)
class Movimiento:
    seccion: str            # 'pago' | 'consumo' | 'impuesto'
    fecha: date
    descripcion: str
    monto: Decimal          # negativo para pagos, bonificaciones y créditos
    moneda: str             # 'ARS' | 'USD'
    cupon: str | None = None
    titular: str | None = None
    cuota_actual: int | None = None
    cuotas_total: int | None = None


@dataclass
class Resumen:
    red: str                # 'visa' | 'mastercard'
    producto: str           # "Visa Signature", "Mastercard Black"
    cuenta: str
    cierre: date
    vencimiento: date
    cierre_anterior: date
    saldo_anterior: dict[str, Decimal]
    saldo_actual: dict[str, Decimal]
    movimientos: list[Movimiento] = field(default_factory=list)


# ──────────────────────────────────────────────
# Lectura del PDF
# ──────────────────────────────────────────────

def lineas_de_pdf(pdf: bytes) -> list[LineaPdf]:
    """Palabras del PDF agrupadas en líneas, en orden de lectura."""
    lineas: list[LineaPdf] = []
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        for pagina in doc.pages:
            # El margen derecho trae el CUIT de BBVA impreso en vertical; esas
            # letras sueltas caen a la altura de cualquier línea y la ensucian.
            palabras = sorted(
                (w for w in pagina.extract_words() if w.get("upright", True)),
                key=lambda w: (round(w["top"]), w["x0"]),
            )
            grupo: list[dict] = []
            for w in palabras:
                if grupo and abs(w["top"] - grupo[0]["top"]) > _TOL_LINEA:
                    lineas.append(_linea(pagina.page_number, grupo))
                    grupo = []
                grupo.append(w)
            if grupo:
                lineas.append(_linea(pagina.page_number, grupo))
    return lineas


def _linea(pagina: int, grupo: list[dict]) -> LineaPdf:
    grupo = sorted(grupo, key=lambda w: w["x0"])
    return LineaPdf(pagina, tuple(Palabra(w["text"], float(w["x1"])) for w in grupo))


# ──────────────────────────────────────────────
# Conversión de valores
# ──────────────────────────────────────────────

def _importe(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


def _fecha(texto: str) -> date | None:
    m = _FECHA_RE.match(texto)
    if not m or m.group(2).lower() not in MESES:
        return None
    return date(2000 + int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))


def _columnas(linea: LineaPdf) -> dict[str, float] | None:
    """Si la línea es un encabezado de importes, el borde derecho de cada columna."""
    textos = {p.texto.upper(): p.x1 for p in linea.palabras}
    if "PESOS" in textos and ("DÓLARES" in textos or "DOLARES" in textos):
        return {"ARS": textos["PESOS"], "USD": textos.get("DÓLARES", textos.get("DOLARES"))}
    return None


def _importes(linea: LineaPdf, columnas: dict[str, float]) -> tuple[list[Palabra], dict[str, Decimal]]:
    """
    Separa la línea en (palabras que no son importes, importes por moneda).

    Un número con forma de importe que no cae en ninguna columna se queda en
    la descripción ("USD 20,00"). Dos importes en la misma columna es un
    formato desconocido.
    """
    resto: list[Palabra] = []
    montos: dict[str, Decimal] = {}
    for p in linea.palabras:
        moneda = None
        if _IMPORTE_RE.match(p.texto):
            moneda = next((m for m, x in columnas.items() if abs(p.x1 - x) <= _TOL_COLUMNA), None)
        if moneda is None:
            resto.append(p)
            continue
        if moneda in montos:
            raise ResumenInvalido(f"Dos importes en la columna {moneda}: {linea.texto!r}")
        montos[moneda] = _importe(p.texto)
    return resto, montos


# ──────────────────────────────────────────────
# Parser
# ──────────────────────────────────────────────

_SECCIONES = (
    ("sus pagos y ajustes realizados", "pago"),
    ("consumos ", "consumo"),
    ("impuestos, cargos e intereses", "impuesto"),
)


def parsear(lineas: list[LineaPdf]) -> Resumen:
    """Arma el resumen y lo valida contra sus propios totales."""
    cab = _cabecera(lineas)

    movimientos: list[Movimiento] = []
    totales_titular: dict[str, dict[str, Decimal]] = {}
    saldo_actual_detalle: dict[str, Decimal] | None = None
    seccion: str | None = None
    titular: str | None = None
    columnas: dict[str, float] | None = None
    en_detalle = False

    for linea in lineas:
        texto = linea.texto
        bajo = texto.lower()

        if not en_detalle:
            en_detalle = texto.strip() == "DETALLE"
            continue
        if bajo.startswith("legales y avisos"):
            break

        nuevas = _columnas(linea)
        if nuevas:
            columnas = nuevas
            continue

        nueva_seccion = next((s for prefijo, s in _SECCIONES if bajo.startswith(prefijo)), None)
        if nueva_seccion and not _FECHA_RE.match(linea.palabras[0].texto):
            seccion = nueva_seccion
            titular = texto[len("Consumos "):].strip() if seccion == "consumo" else None
            continue

        if seccion is None or columnas is None:
            continue
        resto, montos = _importes(linea, columnas)
        if not montos:
            continue  # encabezados de página, texto rotado del margen, etc.

        if bajo.startswith("total consumos de "):
            nombre = " ".join(p.texto for p in resto)[len("TOTAL CONSUMOS DE "):].strip()
            totales_titular[nombre.upper()] = montos
            continue
        if bajo.startswith("saldo actual"):
            saldo_actual_detalle = montos
            continue

        fecha = _fecha(resto[0].texto) if resto else None
        if fecha is None:
            raise ResumenInvalido(f"Línea con importe que no sé leer: {texto!r}")
        if len(montos) != 1:
            raise ResumenInvalido(f"Movimiento con importe en las dos monedas: {texto!r}")

        palabras = resto[1:]
        cupon = None
        if seccion == "consumo" and palabras and _CUPON_RE.match(palabras[-1].texto):
            cupon = palabras.pop().texto
        descripcion = " ".join(p.texto for p in palabras)
        cuota = _CUOTA_RE.search(descripcion)
        (moneda, monto), = montos.items()

        movimientos.append(Movimiento(
            seccion=seccion, fecha=fecha, descripcion=descripcion, monto=monto,
            moneda=moneda, cupon=cupon, titular=titular,
            cuota_actual=int(cuota.group(1)) if cuota else None,
            cuotas_total=int(cuota.group(2)) if cuota else None,
        ))

    resumen = Resumen(**cab, movimientos=movimientos)
    _validar(resumen, totales_titular, saldo_actual_detalle)
    return resumen


def leer_resumen(pdf: bytes) -> Resumen:
    return parsear(lineas_de_pdf(pdf))


def _cabecera(lineas: list[LineaPdf]) -> dict:
    """Datos de la primera página: tarjeta, cuenta, fechas y saldos."""
    textos = [l.texto for l in lineas]
    datos: dict = {}

    for t in textos:
        m = re.search(r"Tarjeta de crédito ((Visa|Mastercard)\b.*)$", t)
        if m:
            datos["producto"] = m.group(1).strip()
            datos["red"] = m.group(2).lower()
            break
    for t in textos:
        m = re.search(r"\bcuenta (\d{6,})\b", t)
        if m:
            datos["cuenta"] = m.group(1)
            break

    datos.update(_fechas_bajo(textos, "CIERRE ACTUAL", ("cierre", "vencimiento")))
    datos.update(_fechas_bajo(textos, "CIERRE ANTERIOR", ("cierre_anterior",)))

    columnas = None
    saldos: dict[str, dict[str, Decimal]] = {}
    for linea in lineas:
        if linea.texto.strip() == "DETALLE":
            break
        nuevas = _columnas(linea)
        if nuevas:
            columnas = nuevas
            continue
        if columnas is None:
            continue
        for clave, prefijo in (("saldo_anterior", "SALDO ANTERIOR"), ("saldo_actual", "SALDO ACTUAL")):
            if linea.texto.startswith(prefijo):
                saldos[clave] = _importes(linea, columnas)[1]
    datos.update(saldos)

    faltan = {"red", "producto", "cuenta", "cierre", "vencimiento", "cierre_anterior",
              "saldo_anterior", "saldo_actual"} - datos.keys()
    if faltan:
        raise ResumenInvalido(f"No encontré en la portada: {', '.join(sorted(faltan))}")
    return datos


def _fechas_bajo(textos: list[str], encabezado: str, claves: tuple[str, ...]) -> dict:
    """Las primeras fechas de la primera línea con fechas después del encabezado."""
    for i, t in enumerate(textos):
        if encabezado in t:
            for siguiente in textos[i + 1:i + 4]:
                fechas = [f for f in (_fecha(x) for x in siguiente.split()) if f]
                if len(fechas) >= len(claves):
                    return dict(zip(claves, fechas))
    return {}


def _validar(r: Resumen, totales_titular: dict, saldo_actual_detalle: dict | None) -> None:
    def suma(**filtro) -> dict[str, Decimal]:
        out = {"ARS": Decimal(0), "USD": Decimal(0)}
        for m in r.movimientos:
            if all(getattr(m, k) == v for k, v in filtro.items()):
                out[m.moneda] += m.monto
        return out

    if not totales_titular:
        raise ResumenInvalido("No encontré el TOTAL CONSUMOS de ningún titular")
    titulares = {(m.titular or "").upper() for m in r.movimientos if m.seccion == "consumo"}
    for nombre, total in totales_titular.items():
        consumos = {"ARS": Decimal(0), "USD": Decimal(0)}
        for m in r.movimientos:
            if m.seccion == "consumo" and (m.titular or "").upper() == nombre:
                consumos[m.moneda] += m.monto
        for moneda in ("ARS", "USD"):
            if consumos[moneda] != total.get(moneda, Decimal(0)):
                raise ResumenInvalido(
                    f"Los consumos de {nombre} en {moneda} suman {consumos[moneda]} "
                    f"y el resumen dice {total.get(moneda, Decimal(0))}"
                )
    if titulares - totales_titular.keys():
        raise ResumenInvalido(f"Consumos sin TOTAL: {', '.join(sorted(titulares - totales_titular.keys()))}")

    if saldo_actual_detalle is None:
        raise ResumenInvalido("No encontré el SALDO ACTUAL del detalle")
    total = suma()
    for moneda in ("ARS", "USD"):
        anterior = r.saldo_anterior.get(moneda, Decimal(0))
        actual = r.saldo_actual.get(moneda, Decimal(0))
        if anterior + total[moneda] != actual:
            raise ResumenInvalido(
                f"En {moneda}: saldo anterior {anterior} + movimientos {total[moneda]} "
                f"no da el saldo actual {actual}"
            )
        if saldo_actual_detalle.get(moneda, Decimal(0)) != actual:
            raise ResumenInvalido(f"El saldo actual en {moneda} de la portada y del detalle no coinciden")
