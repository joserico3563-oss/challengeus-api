"""Migracion La Recocha (aditiva: no borra ni modifica filas existentes).

  python migrar_larecocha.py            -> SOLO LECTURA: muestra lo que haria
  python migrar_larecocha.py --aplicar  -> aplica los cambios
"""
import sys

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable

from database import engine
import crear_bd  # noqa: F401  (registra los modelos existentes)
from crear_bd import Base
from modelos_larecocha import RecompensaModel, TiendaItemModel, CompraModel, InventarioModel

TABLAS = [
    RecompensaModel.__table__,
    TiendaItemModel.__table__,
    CompraModel.__table__,
    InventarioModel.__table__,
]

UQ_EVIDENCIA = "uq_evidencia_bonche_reto_usuario"
SQL_UQ = f"ALTER TABLE evidencias ADD CONSTRAINT {UQ_EVIDENCIA} UNIQUE (bonche_reto_id, usuario_id)"
SQL_DUPLICADOS = (
    "SELECT bonche_reto_id, usuario_id, COUNT(*) AS n FROM evidencias "
    "WHERE bonche_reto_id IS NOT NULL GROUP BY bonche_reto_id, usuario_id HAVING COUNT(*) > 1"
)

# id, nombre, descripcion, precio, tipo, icono, compra unica
SEMILLA = [
    ("double_xp", "Doble XP", "Tu próximo reto completado te da el doble de XP.", 90, "advantage", "bolt", False),
    ("streak_shield", "Escudo de racha", "Protege tu racha si un día no alcanzas a completar el reto.", 120, "advantage", "shield", False),
    ("extra_time", "Tiempo extra", "30 minutos más en la ventana de un reto.", 60, "advantage", "more_time", False),
    ("swap_challenge", "Cambio de reto", "Cambia un reto que no te guste por otro de su misma dificultad.", 80, "advantage", "swap", False),
    ("pick_challenge", "Tú eliges", "Propón el próximo reto para todo el bonche.", 200, "reward", "lightbulb", False),
    ("avatar_frame", "Marco dorado", "Un marco dorado para tu avatar en el Bonche.", 150, "reward", "account_circle", True),
    ("stickers", "Stickers del bonche", "Un pack de stickers para la charla del grupo.", 70, "reward", "celebration", True),
]

SQL_UPSERT = (
    "INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) "
    "VALUES (:id, :name, :description, :price, :kind, :icon, :one_time, TRUE) "
    "ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description), "
    "price = VALUES(price), kind = VALUES(kind), icon = VALUES(icon), one_time = VALUES(one_time)"
)


def indices(conn):
    return {r[2] for r in conn.execute(text("SHOW INDEX FROM evidencias")).fetchall()}


def duplicados(conn):
    return conn.execute(text(SQL_DUPLICADOS)).fetchall()


def main(aplicar):
    modo = "APLICAR" if aplicar else "SOLO LECTURA (no se modifica nada)"
    print(f"=== Migracion La Recocha: {modo} ===\n")
    insp = inspect(engine)

    with engine.connect() as conn:
        print("M1. evidencias: UNIQUE (bonche_reto_id, usuario_id)")
        print("    Filas actuales en evidencias:", conn.execute(text("SELECT COUNT(*) FROM evidencias")).scalar())
        dups = duplicados(conn)
        print("    Duplicados que bloquearian la restriccion:", len(dups))
        for d in dups:
            print("      ", tuple(d))
        existe = UQ_EVIDENCIA in indices(conn)
        print("    Ya existe la restriccion:", existe)
        if not existe:
            print("    SQL:", SQL_UQ)

        print("\nM2. Tablas nuevas (solo se crean las que faltan)")
        for t in TABLAS:
            ya = insp.has_table(t.name)
            print(f"    {t.name}: {'YA EXISTE, se omite' if ya else 'SE CREARA'}")
            if not ya:
                print(str(CreateTable(t).compile(dialect=engine.dialect)).strip())

        print("\nM3. Catalogo de la tienda (upsert por id)")
        for fila in SEMILLA:
            print("    ", fila[0], "-", fila[1], "-", fila[3], "monedas")

        print("\nNo se toca: usuarios, bonches, bonche_retos, retos, votaciones, participacion_votaciones.")

    if not aplicar:
        print("\nSolo lectura terminada. Para aplicar: python migrar_larecocha.py --aplicar")
        return

    with engine.begin() as conn:
        if duplicados(conn):
            raise SystemExit("ABORTADO: hay evidencias duplicadas. No se cambio nada. Revisa la lista de arriba.")
        if UQ_EVIDENCIA not in indices(conn):
            conn.execute(text(SQL_UQ))
            print("M1 aplicada.")
        else:
            print("M1 ya estaba aplicada.")

    Base.metadata.create_all(bind=engine, tables=TABLAS)
    print("M2 aplicada.")

    with engine.begin() as conn:
        for id_, name, desc, price, kind, icon, one in SEMILLA:
            conn.execute(text(SQL_UPSERT), {
                "id": id_, "name": name, "description": desc, "price": price,
                "kind": kind, "icon": icon, "one_time": one,
            })
    print("M3 aplicada.")


if __name__ == "__main__":
    main("--aplicar" in sys.argv)