"""Migración idempotente de la tabla `evidencias`.

Agrega las columnas que `EvidenciaModel` ya declara pero que la tabla en Aiven
no tenía (por eso `POST /api/evidences` devolvía 500), más dos columnas nuevas
necesarias para el almacenamiento real de fotos:

  cloudinary_public_id  -> para poder borrar el archivo al cerrar el reto
  bonche_reto_id        -> el reto concreto del bonche (slot del día)

No borra ni modifica datos existentes: solo agrega columnas e índices que
falten. Se puede ejecutar varias veces sin problema.

Uso:  python migrar_evidencias.py
"""
from sqlalchemy import text

from database import engine

COLUMNAS = [
    ("file_deleted_at", "DATETIME NULL"),
    ("approval_percentage", "INT DEFAULT 0"),
    ("positive_votes", "INT DEFAULT 0"),
    ("negative_votes", "INT DEFAULT 0"),
    ("rewards_processed", "BOOLEAN DEFAULT FALSE"),
    ("cloudinary_public_id", "VARCHAR(255) NULL"),
    ("bonche_reto_id", "VARCHAR(120) NULL"),
]

INDICES = [
    ("ix_evidencias_bonche_reto_id", "bonche_reto_id"),
]


def main():
    with engine.begin() as conn:
        actuales = {f[0] for f in conn.execute(text("SHOW COLUMNS FROM evidencias")).fetchall()}
        for nombre, tipo in COLUMNAS:
            if nombre in actuales:
                print(f"  ya existe: {nombre}")
                continue
            conn.execute(text(f"ALTER TABLE evidencias ADD COLUMN {nombre} {tipo}"))
            print(f"  agregada:  {nombre} {tipo}")

        indices = {r[2] for r in conn.execute(text("SHOW INDEX FROM evidencias")).fetchall()}
        for idx, col in INDICES:
            if idx in indices:
                print(f"  índice ya existe: {idx}")
                continue
            conn.execute(text(f"CREATE INDEX {idx} ON evidencias ({col})"))
            print(f"  índice creado: {idx}")

        print("\nColumnas finales de evidencias:")
        for f in conn.execute(text("SHOW COLUMNS FROM evidencias")).fetchall():
            print(f"  {f[0]:<22} {f[1]:<18} null={f[2]} default={f[4]}")


if __name__ == "__main__":
    main()
