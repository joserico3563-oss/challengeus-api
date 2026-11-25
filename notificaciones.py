# LA_RECOCHA_ENTREGA_FINAL
"""La Recocha: centro de notificaciones internas.

Las notificaciones se guardan en la tabla `notificaciones` y se DERIVAN del
estado real de la base de datos (retos activos, evidencias por calificar,
resultado de las evidencias y recompensas). Este modulo solo LEE las tablas de
votaciones y recompensas: no cambia como se votan, cierran ni pagan los retos.

Evitar duplicados: cada notificacion lleva una `clave` unica por usuario
(UNIQUE usuario_id + clave), asi que sincronizar muchas veces es idempotente.

Futuras push: cada fila guarda `push_estado`, `push_enviada_at` y la
referencia (`ref_tipo`, `ref_id`) para el enlace profundo. Hoy NO se envia
ninguna push. Cuando se implementen, bastara con llamar a `sincronizar` (o a
`_fila`) en el momento del evento y despachar las filas con push NO_ENVIADA.
"""
import uuid
from datetime import timedelta
from typing import List

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from crear_bd import (
    UsuarioModel, RetoModel, EvidenciaModel, IntegranteBoncheModel, BoncheRetoModel,
)
from larecocha import MAX_INTENTOS, ahora_utc, finalizar_pendientes, iso, listar_pendientes
from modelos_larecocha import NotificacionModel, RecompensaModel

# Solo se derivan notificaciones de lo ocurrido en los ultimos 2 dias.
VENTANA = timedelta(days=2)
LIMITE_POR_DEFECTO = 50
LIMITE_MAXIMO = 100
MAX_IDS = 200

NUEVO_RETO = "NEW_CHALLENGE"
VOTOS_PENDIENTES = "VOTES_PENDING"
EVIDENCIA_APROBADA = "EVIDENCE_APPROVED"
EVIDENCIA_RECHAZADA = "EVIDENCE_REJECTED"
SEGUNDO_INTENTO = "RETRY_AVAILABLE"
RECOMPENSA = "REWARD_RECEIVED"
SIN_RECOMPENSA = "NO_REWARD"


def _candidatas(db, uid, ahora):
    """Notificaciones que corresponden HOY al usuario, segun datos reales.

    Devuelve {clave: datos}. Solo mira los bonches a los que pertenece.
    """
    miembro = {
        i.bonche_id: i.joined_at
        for i in db.query(IntegranteBoncheModel).filter(
            IntegranteBoncheModel.usuario_id == uid
        ).all()
    }
    if not miembro:
        return {}
    bonches = list(miembro.keys())
    desde = ahora - VENTANA
    out = {}

    def agregar(clave, tipo, bonche_id, titulo, mensaje, ref_id, creada):
        if clave in out:
            return
        out[clave] = {
            "clave": clave, "tipo": tipo, "bonche_id": bonche_id,
            "titulo": titulo, "mensaje": mensaje,
            "ref_id": ref_id, "creada": creada,
        }

    # 1) Nuevo reto disponible: slots activos ahora en los que puede participar.
    activos = (
        db.query(BoncheRetoModel, RetoModel)
        .join(RetoModel, RetoModel.id == BoncheRetoModel.reto_id)
        .filter(
            BoncheRetoModel.bonche_id.in_(bonches),
            BoncheRetoModel.starts_at <= ahora,
            BoncheRetoModel.ends_at > ahora,
        )
        .all()
    )
    ya_enviados = set()
    if activos:
        ya_enviados = {
            r[0] for r in db.query(EvidenciaModel.bonche_reto_id).filter(
                EvidenciaModel.usuario_id == uid,
                EvidenciaModel.bonche_reto_id.in_([s.id for s, _ in activos]),
            ).all()
        }
    for slot, reto in activos:
        if miembro[slot.bonche_id] >= slot.ends_at:
            continue
        if slot.id in ya_enviados:
            continue
        agregar(
            f"reto:{slot.id}", NUEVO_RETO, slot.bonche_id,
            "¡Nuevo reto disponible!",
            f"«{reto.title}» ya está activo. ¡A cumplirlo con tu bonche!",
            slot.id, max(slot.starts_at, miembro[slot.bonche_id]),
        )

    # 2) Evidencias por calificar (una notificacion por reto, no por foto).
    por_reto = {}
    for p in listar_pendientes(db, uid, ahora):
        por_reto.setdefault(p["boncheRetoId"], p)
    if por_reto:
        bonche_de = {
            s.id: s.bonche_id for s in db.query(BoncheRetoModel).filter(
                BoncheRetoModel.id.in_(list(por_reto.keys()))
            ).all()
        }
        for slot_id, p in por_reto.items():
            agregar(
                f"votos:{slot_id}", VOTOS_PENDIENTES, bonche_de.get(slot_id),
                "Evidencias por calificar",
                f"Tus compa\u00f1eros enviaron evidencias en «{p['challengeTitle']}». "
                "Califícalas para no perder tu recompensa.",
                slot_id, ahora,
            )

    # 3) Resultado de las evidencias propias (aprobada / rechazada / segundo intento).
    filas = (
        db.query(EvidenciaModel, BoncheRetoModel, RetoModel)
        .join(BoncheRetoModel, BoncheRetoModel.id == EvidenciaModel.bonche_reto_id)
        .join(RetoModel, RetoModel.id == BoncheRetoModel.reto_id)
        .filter(
            EvidenciaModel.usuario_id == uid,
            BoncheRetoModel.bonche_id.in_(bonches),
            EvidenciaModel.status.in_(["APPROVED", "REJECTED"]),
            EvidenciaModel.submitted_at >= desde,
        )
        .all()
    )
    if filas:
        slot_ids = list({s.id for _, s, _ in filas})
        intentos = {}
        ultimo = {}
        for sid, n, mx in (
            db.query(
                EvidenciaModel.bonche_reto_id, func.count(EvidenciaModel.id),
                func.max(EvidenciaModel.attempt),
            ).filter(
                EvidenciaModel.usuario_id == uid,
                EvidenciaModel.bonche_reto_id.in_(slot_ids),
            ).group_by(EvidenciaModel.bonche_reto_id).all()
        ):
            intentos[sid] = int(n)
            ultimo[sid] = int(mx or 1)
        con_recompensa = {
            r[0] for r in db.query(RecompensaModel.bonche_reto_id).filter(
                RecompensaModel.usuario_id == uid,
                RecompensaModel.bonche_reto_id.in_(slot_ids),
            ).all()
        }
        for ev, slot, reto in filas:
            if (ev.attempt or 1) < ultimo.get(slot.id, 1):
                continue  # intento ya superado por uno posterior: no avisar
            clave = f"evres:{ev.id}"
            if ev.status == "APPROVED":
                agregar(
                    clave, EVIDENCIA_APROBADA, slot.bonche_id,
                    "Evidencia aprobada",
                    f"Tus compa\u00f1eros aprobaron tu evidencia en «{reto.title}».",
                    slot.id, ahora,
                )
                continue
            # Misma regla que `canRetry` de /challenges/status.
            puede = (
                intentos.get(slot.id, 0) < MAX_INTENTOS
                and ahora < slot.ends_at
                and slot.id not in con_recompensa
            )
            if puede:
                agregar(
                    clave, SEGUNDO_INTENTO, slot.bonche_id,
                    "Segundo intento disponible",
                    f"Rechazaron tu evidencia en «{reto.title}», pero puedes "
                    "enviar un segundo intento mientras el reto siga abierto.",
                    slot.id, ahora,
                )
            else:
                agregar(
                    clave, EVIDENCIA_RECHAZADA, slot.bonche_id,
                    "Evidencia rechazada",
                    f"Tu evidencia en «{reto.title}» no fue aprobada.",
                    slot.id, ahora,
                )

    # 4) Recompensas recibidas (y cierres sin recompensa por no calificar).
    recs = (
        db.query(RecompensaModel, BoncheRetoModel, RetoModel)
        .join(BoncheRetoModel, BoncheRetoModel.id == RecompensaModel.bonche_reto_id)
        .join(RetoModel, RetoModel.id == BoncheRetoModel.reto_id)
        .filter(
            RecompensaModel.usuario_id == uid,
            BoncheRetoModel.bonche_id.in_(bonches),
            RecompensaModel.estado.in_(["PAGADA", "INCUMPLIDA"]),
            RecompensaModel.created_at >= desde,
        )
        .all()
    )
    for r, slot, reto in recs:
        clave = f"rec:{r.id}"
        if r.estado == "PAGADA":
            agregar(
                clave, RECOMPENSA, slot.bonche_id,
                "¡Recompensa recibida!",
                f"Ganaste +{r.xp or 0} XP y +{r.coins or 0} Barras en «{reto.title}».",
                slot.id, r.created_at,
            )
        else:
            agregar(
                clave, SIN_RECOMPENSA, slot.bonche_id,
                "Reto cerrado sin recompensa",
                f"Tu evidencia en «{reto.title}» fue aprobada, pero no "
                "calificaste todas las de tus compa\u00f1eros.",
                slot.id, r.created_at,
            )
    return out


def _fila(uid, c, ahora):
    return NotificacionModel(
        id=f"nt-{uuid.uuid4().hex[:24]}",
        usuario_id=uid,
        bonche_id=c["bonche_id"],
        tipo=c["tipo"],
        titulo=c["titulo"],
        mensaje=c["mensaje"],
        ref_tipo="bonche_reto",
        ref_id=c["ref_id"],
        clave=c["clave"],
        leida=False,
        created_at=min(c["creada"] or ahora, ahora),
        push_estado="NO_ENVIADA",
    )


def sincronizar(db, uid, ahora=None):
    """Crea las notificaciones que falten. Idempotente. Devuelve cuantas creo."""
    ahora = ahora or ahora_utc()
    candidatas = _candidatas(db, uid, ahora)

    # Los avisos temporales dejan de presentarse como acciones pendientes
    # cuando ya no corresponden al estado actual del usuario.
    temporales = {NUEVO_RETO, VOTOS_PENDIENTES, SEGUNDO_INTENTO}
    filas_temporales = db.query(NotificacionModel).filter(
        NotificacionModel.usuario_id == uid,
        NotificacionModel.tipo.in_(temporales),
    ).all()

    actualizadas = False
    for fila in filas_temporales:
        vigente = candidatas.get(fila.clave)

        if vigente is not None and vigente["tipo"] == fila.tipo:
            continue

        if fila.tipo == NUEVO_RETO:
            fila.titulo = "Reto anunciado"
            fila.mensaje = "Este reto ya no tiene una participacion pendiente."
        elif fila.tipo == VOTOS_PENDIENTES:
            fila.titulo = "Aviso de votaciones"
            fila.mensaje = "Ya no tienes votaciones pendientes de este aviso."
        elif fila.tipo == SEGUNDO_INTENTO:
            fila.titulo = "Aviso de segundo intento"
            fila.mensaje = "La oportunidad de segundo intento ya no esta disponible."

        fila.tipo = "OTHER"
        actualizadas = True

    if actualizadas:
        db.commit()

    if not candidatas:
        return 0
    existentes = {
        f[0] for f in db.query(NotificacionModel.clave).filter(
            NotificacionModel.usuario_id == uid,
            NotificacionModel.clave.in_(list(candidatas.keys())),
        ).all()
    }
    nuevas = [c for k, c in candidatas.items() if k not in existentes]
    if not nuevas:
        return 0
    try:
        for c in nuevas:
            db.add(_fila(uid, c, ahora))
        db.commit()
        return len(nuevas)
    except IntegrityError:
        db.rollback()  # otra peticion creo alguna al mismo tiempo: una por una
    creadas = 0
    for c in nuevas:
        try:
            db.add(_fila(uid, c, ahora))
            db.commit()
            creadas += 1
        except IntegrityError:
            db.rollback()
    return creadas


def _a_dict(n):
    return {
        "id": n.id,
        "type": n.tipo,
        "title": n.titulo,
        "message": n.mensaje or "",
        "boncheId": n.bonche_id,
        "refType": n.ref_tipo,
        "refId": n.ref_id,
        "read": bool(n.leida),
        "createdAt": iso(n.created_at),
    }


class LeidasIn(BaseModel):
    ids: List[str]


def registrar_rutas_notificaciones(app, usuario_actual, get_db):

    def visibles(db, uid):
        """Solo notificaciones propias y de bonches a los que sigue perteneciendo."""
        bonches = [
            i[0] for i in db.query(IntegranteBoncheModel.bonche_id).filter(
                IntegranteBoncheModel.usuario_id == uid
            ).all()
        ]
        if bonches:
            alcance = or_(
                NotificacionModel.bonche_id.is_(None),
                NotificacionModel.bonche_id.in_(bonches),
            )
        else:
            alcance = NotificacionModel.bonche_id.is_(None)
        return db.query(NotificacionModel).filter(
            NotificacionModel.usuario_id == uid, alcance
        )

    @app.get("/api/notifications")
    def listar_notificaciones(
        limit: int = LIMITE_POR_DEFECTO,
        yo: UsuarioModel = Depends(usuario_actual),
        db=Depends(get_db),
    ):
        uid = yo.id
        try:
            sincronizar(db, uid)
        except Exception:
            db.rollback()  # un fallo aqui no debe romper el resto de la app
        tope = max(1, min(int(limit), LIMITE_MAXIMO))
        base = visibles(db, uid)
        items = base.order_by(
            NotificacionModel.created_at.desc(), NotificacionModel.id.desc()
        ).limit(tope).all()
        sin_leer = base.filter(NotificacionModel.leida.is_(False)).count()
        return {"items": [_a_dict(n) for n in items], "unreadCount": int(sin_leer)}

    @app.post("/api/notifications/read")
    def marcar_leidas(
        data: LeidasIn,
        yo: UsuarioModel = Depends(usuario_actual),
        db=Depends(get_db),
    ):
        uid = yo.id
        ids = [i for i in data.ids[:MAX_IDS] if i]
        if ids:
            db.query(NotificacionModel).filter(
                NotificacionModel.usuario_id == uid,
                NotificacionModel.id.in_(ids),
                NotificacionModel.leida.is_(False),
            ).update({"leida": True, "leida_at": ahora_utc()}, synchronize_session=False)
            db.commit()
        return {"ok": True}

    @app.post("/api/notifications/read-all")
    def marcar_todas_leidas(
        yo: UsuarioModel = Depends(usuario_actual),
        db=Depends(get_db),
    ):
        uid = yo.id
        db.query(NotificacionModel).filter(
            NotificacionModel.usuario_id == uid,
            NotificacionModel.leida.is_(False),
        ).update({"leida": True, "leida_at": ahora_utc()}, synchronize_session=False)
        db.commit()
        return {"ok": True}
