from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from crear_bd import engine, Base, RetoModel

ALTERS = [
    "ALTER TABLE bonches ADD COLUMN challenges_per_day INT NOT NULL DEFAULT 3",
    "ALTER TABLE bonches ADD COLUMN window_minutes INT NOT NULL DEFAULT 90",
    "ALTER TABLE bonches ADD COLUMN schedule_times VARCHAR(100) NOT NULL DEFAULT '10:00,15:30,20:00'",
    "ALTER TABLE bonches ADD COLUMN tz_offset INT NOT NULL DEFAULT -300",
    "ALTER TABLE bonches ADD COLUMN configured BOOLEAN NOT NULL DEFAULT FALSE",
]

# id, titulo, objetivo, descripcion, categoria, dificultad
CATALOGO = [
    ("cat-01", "Dame un color", "Fotografía algo de color amarillo que tengas cerca.",
     "Busca un objeto amarillo y tómale una foto clara. Vale una fruta, una prenda, un cuaderno... lo importante es que el color se note.",
     "observacion", "facil"),
    ("cat-02", "Arte con lo que hay", "Arma una mini escena creativa con tres objetos.",
     "Junta tres objetos a la mano y organízalos como una pequeña obra de arte. Gana la composición más original.",
     "creatividad", "medio"),
    ("cat-03", "Mano amiga", "Foto de tu mano sosteniendo el objeto más raro que encuentres.",
     "Busca el objeto más inesperado de tu casa y muéstralo sostenido en tu mano.",
     "ingenio", "dificil"),
    ("cat-04", "Sombra con cuento", "Haz una sombra que parezca un animal.",
     "Usa tus manos u objetos y una luz para proyectar la sombra de un animal. Que se entienda cuál es.",
     "creatividad", "medio"),
    ("cat-05", "Tres redondos", "Foto de tres objetos redondos juntos.",
     "Encuentra tres cosas redondas distintas y fotografíalas en la misma imagen.",
     "observacion", "facil"),
    ("cat-06", "El detalle escondido", "Fotografía un detalle de tu entorno que casi nadie notaría.",
     "Mira con calma a tu alrededor y captura algo pequeño que pasa desapercibido todos los días.",
     "observacion", "medio"),
    ("cat-07", "Pose de campeón", "Foto celebrando como si hubieras metido el gol de la final.",
     "Pon tu mejor cara y tu mejor pose de celebración. Se vale gritar, pero la foto debe verse clara.",
     "movimiento", "facil"),
    ("cat-08", "Equilibrio costeño", "Foto con un objeto en equilibrio sobre tu cabeza.",
     "Pon un objeto liviano sobre tu cabeza y tómate la foto sin que se caiga.",
     "movimiento", "dificil"),
    ("cat-09", "Torre de ingenio", "Apila cinco objetos distintos sin que se caigan.",
     "Construye la torre más alta que puedas con cinco objetos diferentes y fotografíala de pie.",
     "ingenio", "medio"),
    ("cat-10", "Cara de mango", "Haz una cara con comida y fotografíala.",
     "Usa frutas, arepas, galletas, lo que haya, para armar una carita con personalidad.",
     "creatividad", "facil"),
    ('cat-11', 'El man del rebusque', 'Inventa un producto completamente inútil.', 'Invéntate un producto con lo que tengas a la mano y preséntalo como si lo estuvieras vendiendo en televisión. ¡Aprovecha, que se acaba!', 'ingenio', 'medio'),
    ('cat-12', 'Tremendo cuadro', 'Recrea una pintura famosa, un meme o una portada musical.', 'Recrea la imagen usando lo que tengas cerca. Aquí no hay presupuesto, pero sí talento.', 'creatividad', 'dificil'),
    ('cat-13', 'Esa vaina tiene cara', 'Encuentra un objeto que parezca tener cara.', 'Mira a tu alrededor y fotografía un objeto que parezca tener rostro. Entre más personalidad tenga esa vaina, mejor.', 'observacion', 'facil'),
    ('cat-14', 'Aquí entre nos', 'Representa un chisme entre dos objetos.', 'Coloca dos objetos como si estuvieran echándose un chisme. Que la foto cuente la historia sin necesidad de palabras.', 'creatividad', 'facil'),
    ('cat-15', 'La última neurona', 'Representa cómo te sientes utilizando objetos.', 'Usa lo que tengas cerca para representar cómo te sientes en este momento. Que el Bonche interprete esa vaina.', 'creatividad', 'medio'),
    ('cat-16', 'Mero susto', 'Recrea tu reacción al creer que perdiste el celular.', 'Pon la cara que pondrías si metes la mano al bolsillo y no encuentras el celular. ¡Nojoda, qué susto!', 'movimiento', 'facil'),
    ('cat-17', 'El propio famoso', 'Imita la pose característica de un personaje famoso.', 'Imita a un cantante, futbolista o personaje famoso. A ver si el Bonche adivina quién eres.', 'movimiento', 'facil'),
    ('cat-18', 'El propio sospechoso', 'Tómate una foto estilo cartel de Se busca.', 'Posa como si acabaras de aparecer en un cartel de Se busca. Esa cara de inocente no engaña a nadie, cuadro.', 'movimiento', 'facil'),
    ('cat-19', 'Mansa aura', 'Captura una pose o situación que desprenda aura.', 'Tírate una pose legendaria o fotografía cualquier vaina que desprenda aura. Aquí se viene a sumar aura, no a perderla.', 'creatividad', 'facil'),
    ('cat-20', 'Sin mirar, cuadro', 'Dibuja un gato con los ojos cerrados.', 'Cierra los ojos, dibuja un gato y fotografía el resultado. Se acepta cualquier aberración artística.', 'ingenio', 'facil'),
    ('cat-21', 'El propio coleccionista', 'Fotografía lo más antiguo que lleves contigo.', 'Busca lo más antiguo que tengas contigo en este momento. A ver qué reliquia cargas encima, cuadro.', 'observacion', 'facil'),
]

PREMIOS = {"facil": (100, 40, 25), "medio": (150, 60, 40), "dificil": (200, 80, 55)}


def main():
    for sql in ALTERS:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
            print("OK:", sql[:70])
        except Exception as e:
            print("Omitido (probablemente ya existe):", sql[:60])

    Base.metadata.create_all(bind=engine)
    print("Tablas verificadas.")

    ahora = datetime.utcnow()
    with Session(engine) as db:
        for rid, titulo, objetivo, descripcion, categoria, dificultad in CATALOGO:
            reto = db.query(RetoModel).filter(RetoModel.id == rid).first()
            if reto is None:
                reto = RetoModel(id=rid, starts_at=ahora, ends_at=ahora)
                db.add(reto)
            puntos, xp, monedas = PREMIOS[dificultad]
            reto.title = titulo
            reto.objective = objetivo
            reto.description = descripcion
            reto.category = categoria
            reto.difficulty = dificultad
            reto.evidence_type = "photo"
            reto.points = puntos
            reto.xp_reward = xp
            reto.coin_reward = monedas
            reto.completed_by = 0
            reto.total_members = 5
        db.commit()
    print("Catálogo de 10 retos listo.")


if __name__ == "__main__":
    main()