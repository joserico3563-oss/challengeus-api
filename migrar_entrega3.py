"""Migracion Entrega 3 (aditiva; no borra filas).

Permite hasta 2 evidencias por jugador y reto:
  1. Agrega evidencias.attempt (INT, por defecto 1).
  2. Crea UNIQUE (bonche_reto_id, usuario_id, attempt).
  3. Quita el UNIQUE anterior (bonche_reto_id, usuario_id).
El orden importa: el indice nuevo se crea ANTES de quitar el viejo.

  python migrar_entrega3.py            -> SOLO LECTURA
  python migrar_entrega3.py --aplicar  -> aplica los cambios
Se puede repetir sin problema (cada paso se omite si ya esta hecho).
"""
import sys

from sqlalchemy import text

from database import engine

NUEVO = "uq_evidencia_slot_usuario_intento"
VIEJO = "uq_evidencia_bonche_reto_usuario"
SQL_COL = "ALTER TABLE evidencias ADD COLUMN attempt INT NOT NULL DEFAULT 1"
SQL_NUEVO = f"ALTER TABLE evidencias ADD CONSTRAINT {NUEVO} UNIQUE (bonche_reto_id, usuario_id, attempt)"
SQL_VIEJO = f"ALTER TABLE evidencias DROP INDEX {VIEJO}"


def estado(conn):
    cols = {r[0] for r in conn.execute(text("SHOW COLUMNS FROM evidencias")).fetchall()}
    idx = {r[2] for r in conn.execute(text("SHOW INDEX FROM evidencias")).fetchall()}
    filas = conn.execute(text("SELECT COUNT(*) FROM evidencias")).scalar()
    return cols, idx, filas


def main(aplicar):
    print("=== Migracion Entrega 3:", "APLICAR" if aplicar else "SOLO LECTURA (no se modifica nada)", "===\n")
    with engine.connect() as conn:
        cols, idx, filas = estado(conn)
    print("Filas en evidencias:", filas)
    print("Columna attempt existe:", "attempt" in cols)
    print("Indice nuevo existe:", NUEVO in idx)
    print("Indice viejo existe:", VIEJO in idx)
    print()
    pasos = []
    if "attempt" not in cols:
        pasos.append(SQL_COL)
    if NUEVO not in idx:
        pasos.append(SQL_NUEVO)
    if VIEJO in idx:
        pasos.append(SQL_VIEJO)
    if not pasos:
        print("Nada que hacer: ya esta todo aplicado.")
        return
    print("SQL que se ejecutaria, en este orden:")
    for p in pasos:
        print("  ", p)
    if not aplicar:
        print("\nSolo lectura terminada. Para aplicar: python migrar_entrega3.py --aplicar")
        return
    for p in pasos:
        with engine.begin() as conn:
            conn.execute(text(p))
        print("OK:", p)
    print("\nMigracion aplicada.")


if __name__ == "__main__":
    main("--aplicar" in sys.argv)