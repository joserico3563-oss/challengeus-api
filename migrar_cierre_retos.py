import sys
from sqlalchemy import inspect, text
from database import engine

columnas = {
    c["name"] for c in inspect(engine).get_columns("bonche_retos")
}

if "closed_at" in columnas:
    print("La columna closed_at ya existe.")
elif "--aplicar" in sys.argv:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE bonche_retos "
            "ADD COLUMN closed_at DATETIME NULL"
        ))
    print("Columna closed_at creada correctamente.")
else:
    print("ALTER TABLE bonche_retos ADD COLUMN closed_at DATETIME NULL;")
    print("SOLO LECTURA: no se modifico la base de datos.")
