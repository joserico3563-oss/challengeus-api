# LA_RECOCHA_ENTREGA_FINAL
"""Migracion Entrega Final: centro de notificaciones (aditiva).

Solo crea la tabla `notificaciones` si no existe. No toca ninguna otra tabla
ni borra filas.

  python migrar_notificaciones.py            -> SOLO LECTURA: muestra lo que haria
  python migrar_notificaciones.py --aplicar  -> crea la tabla
Se puede repetir sin problema.
"""
import sys

from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable

from database import engine
import crear_bd  # noqa: F401  (registra los modelos existentes)
from crear_bd import Base
from modelos_larecocha import NotificacionModel

TABLA = NotificacionModel.__table__
PADRES = ("usuarios", "bonches")


def main(aplicar):
    modo = "APLICAR" if aplicar else "SOLO LECTURA (no se modifica nada)"
    print(f"=== Migracion notificaciones: {modo} ===\n")
    insp = inspect(engine)

    faltan = [t for t in PADRES if not insp.has_table(t)]
    if faltan:
        raise SystemExit("ABORTADO: faltan tablas base: " + ", ".join(faltan))

    if insp.has_table(TABLA.name):
        existentes = {c["name"] for c in insp.get_columns(TABLA.name)}
        esperadas = {c.name for c in TABLA.columns}
        print(f"La tabla {TABLA.name} YA EXISTE, no se hace nada.")
        sobran = esperadas - existentes
        if sobran:
            print("AVISO: le faltan columnas respecto al modelo:", ", ".join(sorted(sobran)))
            print("       Revisa la tabla a mano; este script no la modifica.")
        return

    print(f"La tabla {TABLA.name} SE CREARA con este SQL:\n")
    print(str(CreateTable(TABLA).compile(dialect=engine.dialect)).strip())
    print("\nNo se toca: usuarios, bonches, retos, evidencias, votaciones, recompensas, tienda.")

    if not aplicar:
        print("\nSolo lectura terminada. Para aplicar: python migrar_notificaciones.py --aplicar")
        return

    Base.metadata.create_all(bind=engine, tables=[TABLA])
    print("\nTabla creada.")


if __name__ == "__main__":
    main("--aplicar" in sys.argv)
