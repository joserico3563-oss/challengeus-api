import os
import ssl
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

engine = create_engine(DATABASE_URL, connect_args={"ssl": ssl_context})
Base = declarative_base()

class UsuarioModel(Base):
    __tablename__ = "usuarios"
    id = Column(String(50), primary_key=True, index=True)
    display_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=True)
    xp = Column(Integer, default=0)
    coins = Column(Integer, default=0)
    streak = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)
    completed_challenges = Column(Integer, default=0)

class RetoModel(Base):
    __tablename__ = "retos"
    id = Column(String(50), primary_key=True, index=True)
    title = Column(String(150), nullable=False)
    objective = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)
    difficulty = Column(String(50), nullable=False)
    evidence_type = Column(String(50), nullable=False)
    points = Column(Integer, default=100)
    xp_reward = Column(Integer, default=40)
    coin_reward = Column(Integer, default=25)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    completed_by = Column(Integer, default=0)
    total_members = Column(Integer, default=5)

class BoncheModel(Base):
    __tablename__ = "bonches"
    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    invite_code = Column(String(20), unique=True, index=True, nullable=False)
    leader_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False)
    challenges_per_day = Column(Integer, default=3)
    window_minutes = Column(Integer, default=90)
    schedule_times = Column(String(100), default='10:00,15:30,20:00')
    tz_offset = Column(Integer, default=-300)
    configured = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False)

class IntegranteBoncheModel(Base):
    __tablename__ = "integrantes_bonche"
    id = Column(String(50), primary_key=True, index=True)
    bonche_id = Column(String(50), ForeignKey("bonches.id"), nullable=False)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False)
    role = Column(String(20), default="MEMBER") # LEADER, MEMBER
    joined_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint('bonche_id', 'usuario_id', name='uq_bonche_usuario'),
    )

class EvidenciaModel(Base):
    __tablename__ = "evidencias"
    id = Column(String(50), primary_key=True, index=True)
    reto_id = Column(String(50), ForeignKey("retos.id"), nullable=False)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False)
    image_url = Column(Text, nullable=False)
    status = Column(String(30), default="SUBMITTED")
    submitted_at = Column(DateTime, nullable=False)
    # Reto concreto del bonche (el slot del dia). Permite aislar evidencias
    # entre grupos que ese mismo dia recibieron el mismo reto del catalogo.
    bonche_reto_id = Column(String(120), ForeignKey("bonche_retos.id"), nullable=True)
    # Numero de intento (1 o 2). La 2a evidencia solo se permite si la 1a fue rechazada.
    attempt = Column(Integer, nullable=False, default=1)
    # Referencia en Cloudinary para poder borrar el archivo al cerrar el reto.
    cloudinary_public_id = Column(String(255), nullable=True)
    file_deleted_at = Column(DateTime, nullable=True)
    approval_percentage = Column(Integer, default=0)
    positive_votes = Column(Integer, default=0)
    negative_votes = Column(Integer, default=0)
    rewards_processed = Column(Boolean, default=False)

class VotacionModel(Base):
    __tablename__ = "votaciones"
    id = Column(String(50), primary_key=True, index=True)
    evidencia_id = Column(String(50), ForeignKey("evidencias.id"), nullable=False)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False)
    decision = Column(Boolean, nullable=False)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint('evidencia_id', 'usuario_id', name='uq_evidencia_usuario_voto'),
    )

class ParticipacionVotacionModel(Base):
    __tablename__ = "participacion_votaciones"
    id = Column(String(50), primary_key=True, index=True)
    reto_id = Column(String(50), ForeignKey("retos.id"), nullable=False)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False)
    status = Column(String(30), default="PENDING")
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('reto_id', 'usuario_id', name='uq_reto_usuario_participacion'),
    )

class BoncheRetoModel(Base):
    __tablename__ = "bonche_retos"
    id = Column(String(120), primary_key=True, index=True)
    bonche_id = Column(String(50), ForeignKey("bonches.id"), nullable=False, index=True)
    reto_id = Column(String(50), ForeignKey("retos.id"), nullable=False)
    fecha = Column(String(10), nullable=False)
    slot = Column(Integer, nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint('bonche_id', 'fecha', 'slot', name='uq_bonche_fecha_slot'),
    )
def inicializar_base_de_datos():
    print("Actualizando tablas de Bonches e Integrantes en Aiven...")
    Base.metadata.create_all(bind=engine)
    print("¡Tablas de Bonches creadas exitosamente!")

if __name__ == "__main__":
    inicializar_base_de_datos()