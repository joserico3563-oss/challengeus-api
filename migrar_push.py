import sys
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable
from database import engine
import crear_bd
from modelos_push import DispositivoPushModel

tabla = DispositivoPushModel.__table__

if inspect(engine).has_table(tabla.name):
    print("La tabla dispositivos_push ya existe.")
elif "--aplicar" in sys.argv:
    tabla.create(bind=engine, checkfirst=True)
    print("Tabla dispositivos_push creada correctamente.")
else:
    print(CreateTable(tabla).compile(dialect=engine.dialect))
    print("SOLO LECTURA: no se modifico la base de datos.")
