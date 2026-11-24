from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from crear_bd import Base


class DispositivoPushModel(Base):
    __tablename__ = "dispositivos_push"

    id = Column(String(64), primary_key=True)
    usuario_id = Column(
        String(50), ForeignKey("usuarios.id"),
        nullable=False, index=True
    )
    token = Column(Text, nullable=False)
    plataforma = Column(String(20), nullable=False, default="android")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
