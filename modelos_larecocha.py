from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint

from crear_bd import Base


class RecompensaModel(Base):
    __tablename__ = "recompensas"
    id = Column(String(120), primary_key=True)
    bonche_reto_id = Column(String(120), ForeignKey("bonche_retos.id"), nullable=False, index=True)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False, index=True)
    evidencia_id = Column(String(50), nullable=True)
    estado = Column(String(20), nullable=False)  # PAGADA, RECHAZADA, INCUMPLIDA
    xp = Column(Integer, default=0)
    coins = Column(Integer, default=0)
    visto = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("bonche_reto_id", "usuario_id", name="uq_recompensa_slot_usuario"),
    )


class TiendaItemModel(Base):
    __tablename__ = "tienda_items"
    id = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False)
    kind = Column(String(20), nullable=False)  # advantage, reward
    icon = Column(String(50), nullable=True)
    one_time = Column(Boolean, default=False)
    activo = Column(Boolean, default=True)


class CompraModel(Base):
    __tablename__ = "compras"
    id = Column(String(60), primary_key=True)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False, index=True)
    item_id = Column(String(50), ForeignKey("tienda_items.id"), nullable=False)
    price = Column(Integer, nullable=False)
    request_id = Column(String(80), nullable=False)
    created_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("usuario_id", "request_id", name="uq_compra_usuario_request"),
    )


class InventarioModel(Base):
    __tablename__ = "inventario"
    id = Column(String(120), primary_key=True)
    usuario_id = Column(String(50), ForeignKey("usuarios.id"), nullable=False, index=True)
    item_id = Column(String(50), ForeignKey("tienda_items.id"), nullable=False)
    cantidad = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("usuario_id", "item_id", name="uq_inventario_usuario_item"),
    )