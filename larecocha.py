"""La Recocha: votaciones, recompensas, tienda e inventario.

Se registra desde main.py con registrar_rutas(...). Reglas:
- Evidencias: solo mientras el reto esta activo (se valida en main.py).
- Votos: hasta ends_at + 15 min. No se pueden editar ni repetir.
- Aprobacion: mas del 50 % de votos positivos (minimo un voto valido).
- Recompensas: solo despues de ends_at (el conjunto de evidencias queda cerrado).
  Se pagan cuando la evidencia propia esta aprobada y el usuario voto todas las
  ajenas que le correspondian. A ends_at + 15 min se resuelve todo lo pendiente.
- Idempotente: UNIQUE (bonche_reto_id, usuario_id) en recompensas.
"""
import os
import uuid
from datetime import datetime, timedelta
from typing import List

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError

from crear_bd import (
    UsuarioModel, RetoModel, EvidenciaModel, VotacionModel,
    IntegranteBoncheModel, BoncheRetoModel,
)
from modelos_larecocha import RecompensaModel, TiendaItemModel, CompraModel, InventarioModel

VENTANA_VOTO_EXTRA = timedelta(minutes=15)

MENSAJES_RECOMPENSA = {
    "PAGADA": "¡Tus vales aprobaron tus evidencias, coronaste!",
    "RECHAZADA": "Tu evidencia no fue aprobada esta vez. Sin recompensa.",
    "INCUMPLIDA": "Tu evidencia fue aprobada, pero no calificaste todas las de tus vales. Sin recompensa.",
}


def ahora_utc():
    return datetime.utcnow()


def iso(dt):
    return (dt.isoformat() + "Z") if dt else None


# ------------------------------------------------------------------ nucleo

def votantes_elegibles(db, slot):
    """Integrantes que ya estaban en el bonche cuando empezo el reto."""
    filas = db.query(IntegranteBoncheModel.usuario_id).filter(
        IntegranteBoncheModel.bonche_id == slot.bonche_id,
        IntegranteBoncheModel.joined_at <= slot.starts_at,
    ).all()
    return {f[0] for f in filas}


def resolver_evidencia(db, ev, slot, forzar):
    """Calcula el resultado si ya votaron todos los elegibles (o si se fuerza)."""
    if ev.status != "SUBMITTED":
        return False
    elegibles = votantes_elegibles(db, slot) - {ev.usuario_id}
    votos = db.query(VotacionModel).filter(VotacionModel.evidencia_id == ev.id).all()
    validos = [v for v in votos if v.usuario_id in elegibles]
    completo = len(elegibles) == 0 or len({v.usuario_id for v in validos}) >= len(elegibles)
    if not completo and not forzar:
        return False

    positivos = sum(1 for v in validos if v.decision)
    negativos = len(validos) - positivos
    if len(elegibles) == 0:
        estado, pct = "APPROVED", 100
    elif not validos:
        estado, pct = "NO_VOTES", 0
    else:
        pct = round(positivos * 100 / len(validos))
        estado = "APPROVED" if positivos * 2 > len(validos) else "REJECTED"

    ev.positive_votes = positivos
    ev.negative_votes = negativos
    ev.approval_percentage = pct
    ev.status = estado
    return True


def borrar_foto(public_id):
    import cloudinary
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )
    cloudinary.uploader.destroy(public_id, resource_type="image")


def limpiar_fotos(db, evidencias):
    """Borra de Cloudinary las fotos ya calificadas; conserva los metadatos."""
    claves = ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    if not all(os.getenv(c) for c in claves):
        return
    for ev in evidencias:
        if not ev.cloudinary_public_id or ev.file_deleted_at:
            continue
        try:
            borrar_foto(ev.cloudinary_public_id)
        except Exception:
            continue
        ev.image_url = "[FOTO_ELIMINADA]"
        ev.file_deleted_at = ahora_utc()
    db.commit()


def registrar_recompensa(db, slot, ev, estado, reto, pagar):
    xp = (reto.xp_reward or 0) if pagar else 0
    monedas = (reto.coin_reward or 0) if pagar else 0
    try:
        db.add(RecompensaModel(
            id=f"rc-{uuid.uuid4().hex[:20]}",
            bonche_reto_id=slot.id,
            usuario_id=ev.usuario_id,
            evidencia_id=ev.id,
            estado=estado,
            xp=xp,
            coins=monedas,
            visto=False,
            created_at=ahora_utc(),
        ))
        db.flush()  # si ya existe la fila, el UNIQUE lanza IntegrityError aqui, antes de sumar nada
        if pagar:
            db.execute(
                text(
                    "UPDATE usuarios SET xp = COALESCE(xp, 0) + :xp, "
                    "coins = COALESCE(coins, 0) + :c, "
                    "completed_challenges = COALESCE(completed_challenges, 0) + 1 "
                    "WHERE id = :u"
                ),
                {"xp": xp, "c": monedas, "u": ev.usuario_id},
            )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def procesar_slot(db, slot, ahora=None):
    """Resuelve evidencias y reparte recompensas de un reto del bonche."""
    ahora = ahora or ahora_utc()
    db.commit()  # snapshot nuevo: ve los votos confirmados por otras peticiones
    if ahora < slot.ends_at:
        return  # el conjunto de evidencias aun no esta cerrado
    cierre_total = ahora >= slot.ends_at + VENTANA_VOTO_EXTRA

    evs = db.query(EvidenciaModel).filter(
        EvidenciaModel.bonche_reto_id == slot.id
    ).with_for_update().all()
    if not evs:
        db.rollback()
        return
    resueltas = [ev for ev in evs if resolver_evidencia(db, ev, slot, cierre_total)]
    db.commit()

    evs = db.query(EvidenciaModel).filter(EvidenciaModel.bonche_reto_id == slot.id).all()
    reto = db.query(RetoModel).filter(RetoModel.id == slot.reto_id).first()
    if reto is not None:
        elegibles = votantes_elegibles(db, slot)
        ids = [e.id for e in evs]
        hechos = {}
        for v in db.query(VotacionModel).filter(VotacionModel.evidencia_id.in_(ids)).all():
            hechos.setdefault(v.usuario_id, set()).add(v.evidencia_id)
        ya = {
            r[0] for r in db.query(RecompensaModel.usuario_id).filter(
                RecompensaModel.bonche_reto_id == slot.id
            ).all()
        }
        for ev in evs:
            if ev.usuario_id in ya or ev.status == "SUBMITTED":
                continue
            if ev.status != "APPROVED":
                registrar_recompensa(db, slot, ev, "RECHAZADA", reto, False)
                continue
            if ev.usuario_id in elegibles:
                debe = {e.id for e in evs if e.usuario_id != ev.usuario_id}
            else:
                debe = set()
            if debe.issubset(hechos.get(ev.usuario_id, set())):
                registrar_recompensa(db, slot, ev, "PAGADA", reto, True)
            elif cierre_total:
                registrar_recompensa(db, slot, ev, "INCUMPLIDA", reto, False)

    if resueltas:
        limpiar_fotos(db, resueltas)


def finalizar_pendientes(db, usuario_id):
    """Cierre perezoso: procesa los retos vencidos de los bonches del usuario."""
    ahora = ahora_utc()
    bonches = [
        i[0] for i in db.query(IntegranteBoncheModel.bonche_id).filter(
            IntegranteBoncheModel.usuario_id == usuario_id
        ).all()
    ]
    if not bonches:
        return
    sin_resultado = ~db.query(RecompensaModel.id).filter(
        RecompensaModel.bonche_reto_id == EvidenciaModel.bonche_reto_id,
        RecompensaModel.usuario_id == EvidenciaModel.usuario_id,
    ).exists()
    ids = [
        r[0] for r in db.query(EvidenciaModel.bonche_reto_id)
        .join(BoncheRetoModel, BoncheRetoModel.id == EvidenciaModel.bonche_reto_id)
        .filter(
            BoncheRetoModel.bonche_id.in_(bonches),
            BoncheRetoModel.ends_at <= ahora,
            sin_resultado,
        )
        .distinct().all()
    ]
    for sid in ids:
        slot = db.query(BoncheRetoModel).filter(BoncheRetoModel.id == sid).first()
        if slot is not None:
            procesar_slot(db, slot, ahora)


def listar_pendientes(db, usuario_id, ahora):
    miembro = {
        i.bonche_id: i.joined_at for i in db.query(IntegranteBoncheModel).filter(
            IntegranteBoncheModel.usuario_id == usuario_id
        ).all()
    }
    if not miembro:
        return []
    ya_voto = {
        v[0] for v in db.query(VotacionModel.evidencia_id).filter(
            VotacionModel.usuario_id == usuario_id
        ).all()
    }
    filas = (
        db.query(EvidenciaModel, BoncheRetoModel, UsuarioModel, RetoModel)
        .join(BoncheRetoModel, BoncheRetoModel.id == EvidenciaModel.bonche_reto_id)
        .join(UsuarioModel, UsuarioModel.id == EvidenciaModel.usuario_id)
        .join(RetoModel, RetoModel.id == BoncheRetoModel.reto_id)
        .filter(
            EvidenciaModel.status == "SUBMITTED",
            EvidenciaModel.usuario_id != usuario_id,
            BoncheRetoModel.bonche_id.in_(list(miembro.keys())),
            BoncheRetoModel.ends_at > ahora - VENTANA_VOTO_EXTRA,
        )
        .order_by(EvidenciaModel.submitted_at)
        .all()
    )
    salida = []
    for ev, slot, dueno, reto in filas:
        if ev.id in ya_voto:
            continue
        if miembro[slot.bonche_id] > slot.starts_at:
            continue  # entro al bonche despues de que empezo ese reto
        if not ev.image_url or ev.image_url.startswith("["):
            continue
        salida.append({
            "evidenceId": ev.id,
            "boncheRetoId": slot.id,
            "imageUrl": ev.image_url,
            "ownerId": dueno.id,
            "ownerName": dueno.display_name,
            "challengeTitle": reto.title,
            "votingEndsAt": iso(slot.ends_at + VENTANA_VOTO_EXTRA),
        })
    return salida


# ------------------------------------------------------------------ tienda

def mensaje_compra(item):
    if item.id == "double_xp":
        return "¡Compraste Doble XP! Tu próxima recompensa tendrá el doble de experiencia."
    return f"¡Compraste {item.name}! Queda guardado en tu inventario."


class VotoIn(BaseModel):
    evidence_id: str
    approve: bool


class VistasIn(BaseModel):
    ids: List[str]


class CompraIn(BaseModel):
    item_id: str
    request_id: str


def registrar_rutas(app, usuario_actual, get_db, usuario_dict):

    def es_miembro(db, bonche_id, usuario_id):
        return db.query(IntegranteBoncheModel).filter(
            IntegranteBoncheModel.bonche_id == bonche_id,
            IntegranteBoncheModel.usuario_id == usuario_id,
        ).first() is not None

    # ---------------------------------------------------------------- perfil

    @app.get("/api/me")
    def mi_perfil(yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        uid = yo.id
        finalizar_pendientes(db, uid)
        actual = db.query(UsuarioModel).filter(UsuarioModel.id == uid).first()
        return usuario_dict(actual)

    # --------------------------------------------------------------- votos

    @app.get("/api/votes/pending")
    def votos_pendientes(yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        uid = yo.id
        finalizar_pendientes(db, uid)
        return {"items": listar_pendientes(db, uid, ahora_utc())}

    @app.post("/api/votes")
    def votar(data: VotoIn, yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        uid = yo.id
        ahora = ahora_utc()
        db.commit()  # cierra la lectura del usuario: el bloqueo de abajo ve datos frescos

        ev = db.query(EvidenciaModel).filter(
            EvidenciaModel.id == data.evidence_id
        ).with_for_update().first()
        if ev is None or not ev.bonche_reto_id:
            db.rollback()
            raise HTTPException(status_code=404, detail="Evidencia no encontrada.")
        slot = db.query(BoncheRetoModel).filter(BoncheRetoModel.id == ev.bonche_reto_id).first()
        if slot is None:
            db.rollback()
            raise HTTPException(status_code=404, detail="Reto no encontrado.")
        if ev.usuario_id == uid:
            db.rollback()
            raise HTTPException(status_code=403, detail="No puedes calificar tu propia evidencia.")
        if uid not in votantes_elegibles(db, slot):
            db.rollback()
            raise HTTPException(status_code=403, detail="No te corresponde calificar esta evidencia.")
        if ahora >= slot.ends_at + VENTANA_VOTO_EXTRA:
            db.rollback()
            raise HTTPException(status_code=400, detail="La votación de este reto ya cerró.")
        if ev.status != "SUBMITTED":
            db.rollback()
            raise HTTPException(status_code=400, detail="Esta evidencia ya fue calificada.")
        previo = db.query(VotacionModel).filter(
            VotacionModel.evidencia_id == ev.id, VotacionModel.usuario_id == uid
        ).first()
        if previo is not None:
            db.rollback()
            raise HTTPException(status_code=409, detail="Ya calificaste esta evidencia.")

        try:
            db.add(VotacionModel(
                id=f"vt-{uuid.uuid4().hex[:20]}",
                evidencia_id=ev.id,
                usuario_id=uid,
                decision=bool(data.approve),
                created_at=ahora,
            ))
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Ya calificaste esta evidencia.")

        resuelta = resolver_evidencia(db, ev, slot, False)
        db.commit()
        if resuelta:
            limpiar_fotos(db, [ev])
        procesar_slot(db, slot, ahora)
        return {"ok": True, "pendientes": len(listar_pendientes(db, uid, ahora_utc()))}

    # --------------------------------------------------------- recompensas

    @app.get("/api/rewards/unseen")
    def recompensas_no_vistas(yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        uid = yo.id
        finalizar_pendientes(db, uid)
        filas = (
            db.query(RecompensaModel, RetoModel)
            .join(BoncheRetoModel, BoncheRetoModel.id == RecompensaModel.bonche_reto_id)
            .join(RetoModel, RetoModel.id == BoncheRetoModel.reto_id)
            .filter(RecompensaModel.usuario_id == uid, RecompensaModel.visto.is_(False))
            .order_by(RecompensaModel.created_at)
            .all()
        )
        return [
            {
                "id": r.id,
                "estado": r.estado,
                "xp": r.xp or 0,
                "coins": r.coins or 0,
                "challengeTitle": reto.title,
                "message": MENSAJES_RECOMPENSA.get(r.estado, ""),
            }
            for r, reto in filas
        ]

    @app.post("/api/rewards/seen")
    def recompensas_vistas(data: VistasIn, yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        uid = yo.id
        if data.ids:
            db.query(RecompensaModel).filter(
                RecompensaModel.usuario_id == uid,
                RecompensaModel.id.in_(data.ids),
            ).update({"visto": True}, synchronize_session=False)
            db.commit()
        return {"ok": True}

    # ------------------------------------------------- estado de los retos

    @app.get("/api/bonches/{bonche_id}/challenges/status")
    def estado_retos(bonche_id: str, yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        uid = yo.id
        if not es_miembro(db, bonche_id, uid):
            raise HTTPException(status_code=403, detail="No perteneces a este bonche.")
        finalizar_pendientes(db, uid)
        desde = ahora_utc() - timedelta(days=1)
        ids = [
            s[0] for s in db.query(BoncheRetoModel.id).filter(
                BoncheRetoModel.bonche_id == bonche_id,
                BoncheRetoModel.ends_at > desde,
            ).all()
        ]
        if not ids:
            return []
        propias = {
            e.bonche_reto_id: e for e in db.query(EvidenciaModel).filter(
                EvidenciaModel.bonche_reto_id.in_(ids), EvidenciaModel.usuario_id == uid
            ).all()
        }
        conteo = dict(
            db.query(EvidenciaModel.bonche_reto_id, func.count(EvidenciaModel.id))
            .filter(EvidenciaModel.bonche_reto_id.in_(ids))
            .group_by(EvidenciaModel.bonche_reto_id).all()
        )
        recompensas = {
            r.bonche_reto_id: r.estado for r in db.query(RecompensaModel).filter(
                RecompensaModel.bonche_reto_id.in_(ids), RecompensaModel.usuario_id == uid
            ).all()
        }
        return [
            {
                "boncheRetoId": sid,
                "submitted": sid in propias,
                "evidenceStatus": propias[sid].status if sid in propias else None,
                "reward": recompensas.get(sid),
                "submittedCount": int(conteo.get(sid, 0)),
            }
            for sid in ids
        ]

    # --------------------------------------------------------------- tienda

    @app.get("/api/store/items")
    def tienda_items(yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        items = db.query(TiendaItemModel).filter(
            TiendaItemModel.activo.is_(True)
        ).order_by(TiendaItemModel.price).all()
        return [
            {
                "id": i.id, "name": i.name, "description": i.description or "",
                "price": i.price, "kind": i.kind, "icon": i.icon or "",
                "oneTime": bool(i.one_time),
            }
            for i in items
        ]

    @app.get("/api/inventory")
    def inventario(yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        filas = (
            db.query(InventarioModel, TiendaItemModel)
            .join(TiendaItemModel, TiendaItemModel.id == InventarioModel.item_id)
            .filter(InventarioModel.usuario_id == yo.id, InventarioModel.cantidad > 0)
            .all()
        )
        return [
            {"itemId": inv.item_id, "name": it.name, "quantity": inv.cantidad}
            for inv, it in filas
        ]

    def respuesta_compra(db, uid, item, repetida):
        monedas = db.query(UsuarioModel.coins).filter(UsuarioModel.id == uid).scalar() or 0
        cantidad = db.query(InventarioModel.cantidad).filter(
            InventarioModel.usuario_id == uid, InventarioModel.item_id == item.id
        ).scalar() or 0
        return {
            "message": mensaje_compra(item),
            "coins": int(monedas),
            "itemId": item.id,
            "quantity": int(cantidad),
            "repeated": repetida,
        }

    @app.post("/api/store/purchase")
    def comprar(data: CompraIn, yo: UsuarioModel = Depends(usuario_actual), db=Depends(get_db)):
        uid = yo.id
        rid = data.request_id.strip()
        if not (8 <= len(rid) <= 80):
            raise HTTPException(status_code=400, detail="Identificador de compra inválido.")
        item = db.query(TiendaItemModel).filter(TiendaItemModel.id == data.item_id).first()
        if item is None or not item.activo:
            raise HTTPException(status_code=404, detail="Ese artículo no existe.")

        previa = db.query(CompraModel).filter(
            CompraModel.usuario_id == uid, CompraModel.request_id == rid
        ).first()
        if previa is not None:
            return respuesta_compra(db, uid, item, True)

        try:
            db.add(CompraModel(
                id=f"cp-{uuid.uuid4().hex[:20]}",
                usuario_id=uid, item_id=item.id, price=item.price,
                request_id=rid, created_at=ahora_utc(),
            ))
            db.flush()
            res = db.execute(
                text("UPDATE usuarios SET coins = coins - :p WHERE id = :u AND coins >= :p"),
                {"p": item.price, "u": uid},
            )
            if res.rowcount != 1:
                db.rollback()
                raise HTTPException(status_code=402, detail="No te alcanzan las monedas.")
            inv_id = f"inv-{uid}-{item.id}"[:120]
            if item.one_time:
                db.execute(
                    text("INSERT INTO inventario (id, usuario_id, item_id, cantidad) VALUES (:i, :u, :it, 1)"),
                    {"i": inv_id, "u": uid, "it": item.id},
                )
            else:
                db.execute(
                    text(
                        "INSERT INTO inventario (id, usuario_id, item_id, cantidad) VALUES (:i, :u, :it, 1) "
                        "ON DUPLICATE KEY UPDATE cantidad = cantidad + 1"
                    ),
                    {"i": inv_id, "u": uid, "it": item.id},
                )
            db.commit()
        except IntegrityError:
            db.rollback()
            previa = db.query(CompraModel).filter(
                CompraModel.usuario_id == uid, CompraModel.request_id == rid
            ).first()
            if previa is not None:
                return respuesta_compra(db, uid, item, True)
            if item.one_time:
                raise HTTPException(status_code=409, detail="Ya tienes este artículo.")
            raise HTTPException(status_code=409, detail="No pudimos completar la compra. Inténtalo de nuevo.")

        return respuesta_compra(db, uid, item, False)