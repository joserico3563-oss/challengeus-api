"""La Recocha: votaciones, recompensas, ranking, tienda e inventario (Entrega 3).

Reglas:
- Evidencias: hasta 2 por jugador y reto. La 2a solo si la 1a fue rechazada y queda tiempo.
- Votos: hasta ends_at + 15 min. No se editan ni se repiten.
- Aprobacion: votos positivos / votos validos >= 50 % (el empate aprueba).
- Una evidencia se resuelve cuando votaron todos los elegibles o al cierre por tiempo.
- Cierre anticipado: todos los elegibles tienen su ultima evidencia aprobada y no queda ninguna en votacion.
- Cierre por tiempo: ends_at + 15 min, solo con los votos recibidos.
- Evidencia sin ningun voto: 50 % de XP y monedas. Rechazada o sin evidencia: nada.
- Las recompensas se pagan una sola vez, al cierre (UNIQUE bonche_reto_id + usuario_id).
"""
import calendar
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
    IntegranteBoncheModel, BoncheRetoModel, BoncheModel,
)
from modelos_larecocha import RecompensaModel, TiendaItemModel, CompraModel, InventarioModel

VENTANA_VOTO_EXTRA = timedelta(minutes=15)
MAX_INTENTOS = 2
OFFSET_POR_DEFECTO = -300

MENSAJES_RECOMPENSA = {
    "PAGADA": "\u00a1Tus vales aprobaron tus evidencias, coronaste!",
    "RECHAZADA": "Tu evidencia no fue aprobada. Sin recompensa en este reto.",
    "INCUMPLIDA": "Tu evidencia fue aprobada, pero no calificaste todas las de tus vales. Sin recompensa.",
}
MENSAJE_MITAD = "Tu evidencia era v\u00e1lida, pero nadie alcanz\u00f3 a calificarla: recibes el 50 % de la recompensa."

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
MESES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def ahora_utc():
    return datetime.utcnow()


def iso(dt):
    return (dt.isoformat() + "Z") if dt else None


# ------------------------------------------------------------------ nucleo

def votantes_elegibles(db, slot):
    """Integrantes que ingresaron al bonche antes de terminar el reto."""
    filas = db.query(IntegranteBoncheModel.usuario_id).filter(
        IntegranteBoncheModel.bonche_id == slot.bonche_id,
        IntegranteBoncheModel.joined_at < slot.ends_at,
    ).all()
    return {f[0] for f in filas}


def resolver_evidencia(db, ev, slot, forzar):
    """Calcula el resultado si votaron todos los elegibles (o si se fuerza por cierre)."""
    if ev.status != "SUBMITTED":
        return False
    elegibles = votantes_elegibles(db, slot) - {ev.usuario_id}
    votos = db.query(VotacionModel).filter(VotacionModel.evidencia_id == ev.id).all()
    validos = [v for v in votos if v.usuario_id != ev.usuario_id]
    votantes = {v.usuario_id for v in validos}
    completo = elegibles.issubset(votantes)
    if not completo and not forzar:
        return False

    positivos = sum(1 for v in validos if v.decision)
    negativos = len(validos) - positivos
    if len(elegibles) == 0 and not validos:
        estado, pct = "APPROVED", 100
    elif not validos:
        estado, pct = "NO_VOTES", 0
    else:
        pct = round(positivos * 100 / len(validos))
        estado = "APPROVED" if positivos * 2 >= len(validos) else "REJECTED"

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
    """Borra de Cloudinary las fotos de evidencias ya resueltas. Nunca las que siguen en votacion."""
    claves = ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    if not all(os.getenv(c) for c in claves):
        return
    for ev in evidencias:
        if ev.status == "SUBMITTED":
            continue
        if not ev.cloudinary_public_id or ev.file_deleted_at:
            continue
        try:
            borrar_foto(ev.cloudinary_public_id)
        except Exception:
            continue
        ev.image_url = "[FOTO_ELIMINADA]"
        ev.file_deleted_at = ahora_utc()
    db.commit()


def registrar_recompensa(db, slot_id, usuario_id, evidencia_id, estado, xp, monedas):
    try:
        db.add(RecompensaModel(
            id=f"rc-{uuid.uuid4().hex[:20]}",
            bonche_reto_id=slot_id,
            usuario_id=usuario_id,
            evidencia_id=evidencia_id,
            estado=estado,
            xp=xp,
            coins=monedas,
            visto=False,
            created_at=ahora_utc(),
        ))
        db.flush()  # si la fila ya existe, el UNIQUE falla aqui, antes de sumar nada
        if estado == "PAGADA":
            db.execute(
                text(
                    "UPDATE usuarios SET xp = COALESCE(xp, 0) + :xp, "
                    "coins = COALESCE(coins, 0) + :c, "
                    "completed_challenges = COALESCE(completed_challenges, 0) + 1 "
                    "WHERE id = :u"
                ),
                {"xp": xp, "c": monedas, "u": usuario_id},
            )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def procesar_slot(db, slot, ahora=None):
    """Resuelve evidencias y, si corresponde, cierra el reto y reparte recompensas."""
    ahora = ahora or ahora_utc()
    slot_id = slot.id
    db.commit()  # snapshot nuevo: ve los votos confirmados por otras peticiones
    if ahora < slot.starts_at:
        return
    cierre_total = ahora >= slot.ends_at + VENTANA_VOTO_EXTRA

    evs = db.query(EvidenciaModel).filter(
        EvidenciaModel.bonche_reto_id == slot_id
    ).with_for_update().all()
    if not evs:
        db.rollback()
        return
    for ev in evs:
        resolver_evidencia(db, ev, slot, cierre_total)
    db.commit()

    evs = db.query(EvidenciaModel).filter(EvidenciaModel.bonche_reto_id == slot_id).all()
    elegibles = votantes_elegibles(db, slot)

    ultimo = {}
    for ev in evs:
        previo = ultimo.get(ev.usuario_id)
        if previo is None or (ev.attempt or 1) > (previo.attempt or 1):
            ultimo[ev.usuario_id] = ev
    resumen = {uid: (ev.id, ev.status) for uid, ev in ultimo.items()}
    sin_resolver = any(e.status == "SUBMITTED" for e in evs)

    if not cierre_total:
        todos = bool(elegibles) and all(
            u in resumen and resumen[u][1] == "APPROVED" for u in elegibles
        )
        if not todos or sin_resolver:
            return  # el reto sigue abierto: nada se paga todavia

    reto = db.query(RetoModel).filter(RetoModel.id == slot.reto_id).first()
    if reto is None:
        return
    xp_base = reto.xp_reward or 0
    coins_base = reto.coin_reward or 0

    duenos = {e.id: e.usuario_id for e in evs}
    hechos = {}
    for v in db.query(VotacionModel).filter(VotacionModel.evidencia_id.in_(list(duenos.keys()))).all():
        hechos.setdefault(v.usuario_id, set()).add(v.evidencia_id)
    ya = {
        r[0] for r in db.query(RecompensaModel.usuario_id).filter(
            RecompensaModel.bonche_reto_id == slot_id
        ).all()
    }

    for uid, (evid, estado_ev) in resumen.items():
        if uid in ya:
            continue
        if estado_ev not in ("APPROVED", "NO_VOTES"):
            registrar_recompensa(db, slot_id, uid, evid, "RECHAZADA", 0, 0)
            continue
        if uid not in elegibles:
            registrar_recompensa(db, slot_id, uid, evid, "INCUMPLIDA", 0, 0)
            continue

        ingreso = db.query(IntegranteBoncheModel.joined_at).filter(
            IntegranteBoncheModel.bonche_id == slot.bonche_id,
            IntegranteBoncheModel.usuario_id == uid,
        ).scalar()

        if ingreso is None:
            continue

        debe = {
            e.id for e in evs
            if e.usuario_id != uid
            and (
                ingreso <= slot.starts_at
                or e.submitted_at >= ingreso
            )
        }
        if not debe.issubset(hechos.get(uid, set())):
            registrar_recompensa(db, slot_id, uid, evid, "INCUMPLIDA", 0, 0)
            continue
        if estado_ev == "APPROVED":
            registrar_recompensa(db, slot_id, uid, evid, "PAGADA", xp_base, coins_base)
        else:
            registrar_recompensa(db, slot_id, uid, evid, "PAGADA", xp_base // 2, coins_base // 2)

    limpiar_fotos(
        db,
        db.query(EvidenciaModel).filter(EvidenciaModel.bonche_reto_id == slot_id).all(),
    )


def finalizar_pendientes(db, usuario_id):
    """Cierre perezoso: procesa los retos con evidencias de los bonches del usuario."""
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
            BoncheRetoModel.starts_at <= ahora,
            BoncheRetoModel.ends_at > ahora - timedelta(days=2),
            sin_resultado,
        )
        .distinct().all()
    ]
    for sid in ids:
        slot = db.query(BoncheRetoModel).filter(BoncheRetoModel.id == sid).first()
        if slot is not None:
            procesar_slot(db, slot, ahora)

    # Barrido: fotos de retos ya cerrados que no se alcanzaron a borrar.
    cerrada = db.query(RecompensaModel.id).filter(
        RecompensaModel.bonche_reto_id == EvidenciaModel.bonche_reto_id,
        RecompensaModel.usuario_id == EvidenciaModel.usuario_id,
    ).exists()
    huerfanas = (
        db.query(EvidenciaModel)
        .join(BoncheRetoModel, BoncheRetoModel.id == EvidenciaModel.bonche_reto_id)
        .filter(
            BoncheRetoModel.bonche_id.in_(bonches),
            EvidenciaModel.cloudinary_public_id.isnot(None),
            EvidenciaModel.file_deleted_at.is_(None),
            EvidenciaModel.status != "SUBMITTED",
            cerrada,
        )
        .limit(5).all()
    )
    if huerfanas:
        limpiar_fotos(db, huerfanas)


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
        if miembro[slot.bonche_id] >= slot.ends_at:
            continue  # ingreso despues del cierre del reto
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


# ----------------------------------------------------------------- ranking

def rango_periodo(ahora_local, periodo, atras=0):
    """Inicio y fin (hora local del bonche) del periodo actual o de uno anterior."""
    if periodo == "weekly":
        lunes = datetime(ahora_local.year, ahora_local.month, ahora_local.day) - timedelta(days=ahora_local.weekday())
        inicio = lunes - timedelta(days=7 * atras)
        return inicio, inicio + timedelta(days=7)
    mes = ahora_local.year * 12 + (ahora_local.month - 1) - atras
    anio, m0 = divmod(mes, 12)
    a2, m2 = divmod(mes + 1, 12)
    return datetime(anio, m0 + 1, 1), datetime(a2, m2 + 1, 1)


def etiqueta_periodo(periodo, ini, fin):
    if periodo == "monthly":
        return f"{MESES[ini.month - 1]} {ini.year}"
    ult = fin - timedelta(days=1)
    if ini.month == ult.month:
        return f"Semana del {ini.day}-{ult.day} {MESES_CORTO[ult.month - 1]}"
    return f"Semana del {ini.day} {MESES_CORTO[ini.month - 1]} - {ult.day} {MESES_CORTO[ult.month - 1]}"


def filas_periodo(db, bonche_id, ini_local, fin_local, offset):
    """XP pagada en el bonche durante el periodo (por la hora de inicio del reto)."""
    ini = ini_local - offset
    fin = fin_local - offset
    return (
        db.query(RecompensaModel.usuario_id, RecompensaModel.xp, BoncheRetoModel.starts_at)
        .join(BoncheRetoModel, BoncheRetoModel.id == RecompensaModel.bonche_reto_id)
        .filter(
            BoncheRetoModel.bonche_id == bonche_id,
            RecompensaModel.estado == "PAGADA",
            BoncheRetoModel.starts_at >= ini,
            BoncheRetoModel.starts_at < fin,
        )
        .all()
    )


def clasificar(miembros, filas):
    xp = {}
    hechos = {}
    for uid, puntos, _ in filas:
        xp[uid] = xp.get(uid, 0) + (puntos or 0)
        hechos[uid] = hechos.get(uid, 0) + 1
    tabla = [
        {"userId": uid, "name": nombre, "xp": xp.get(uid, 0), "completed": hechos.get(uid, 0), "_unio": unio}
        for uid, nombre, unio in miembros
    ]
    tabla.sort(key=lambda f: (-f["xp"], -f["completed"], f["_unio"], f["userId"]))
    for i, f in enumerate(tabla, start=1):
        f["rank"] = i
        del f["_unio"]
    return tabla


# ------------------------------------------------------------------ tienda

def mensaje_compra(item):
    if item.id == "double_xp":
        return "\u00a1Compraste Doble XP! Tu pr\u00f3xima recompensa tendr\u00e1 el doble de experiencia."
    return f"\u00a1Compraste {item.name}! Queda guardado en tu inventario."


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
        db.commit()

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
            raise HTTPException(status_code=400, detail="La votaci\u00f3n de este reto ya cerr\u00f3.")
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

        resolver_evidencia(db, ev, slot, False)
        db.commit()
        procesar_slot(db, slot, ahora)  # puede cerrar el reto antes de tiempo
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
        salida = []
        for r, reto in filas:
            mensaje = MENSAJES_RECOMPENSA.get(r.estado, "")
            if r.estado == "PAGADA" and (r.xp or 0) < (reto.xp_reward or 0):
                mensaje = MENSAJE_MITAD
            salida.append({
                "id": r.id,
                "estado": r.estado,
                "xp": r.xp or 0,
                "coins": r.coins or 0,
                "challengeTitle": reto.title,
                "message": mensaje,
            })
        return salida

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
        ahora = ahora_utc()
        desde = ahora - timedelta(days=1)
        slots = {
            s.id: s for s in db.query(BoncheRetoModel).filter(
                BoncheRetoModel.bonche_id == bonche_id,
                BoncheRetoModel.ends_at > desde,
            ).all()
        }
        ids = list(slots.keys())
        if not ids:
            return []
        propias = {}
        intentos = {}
        for e in db.query(EvidenciaModel).filter(
            EvidenciaModel.bonche_reto_id.in_(ids), EvidenciaModel.usuario_id == uid
        ).all():
            intentos[e.bonche_reto_id] = intentos.get(e.bonche_reto_id, 0) + 1
            previo = propias.get(e.bonche_reto_id)
            if previo is None or (e.attempt or 1) > (previo.attempt or 1):
                propias[e.bonche_reto_id] = e
        conteo = dict(
            db.query(EvidenciaModel.bonche_reto_id, func.count(func.distinct(EvidenciaModel.usuario_id)))
            .filter(EvidenciaModel.bonche_reto_id.in_(ids))
            .group_by(EvidenciaModel.bonche_reto_id).all()
        )
        recompensas = {
            r.bonche_reto_id: r.estado for r in db.query(RecompensaModel).filter(
                RecompensaModel.bonche_reto_id.in_(ids), RecompensaModel.usuario_id == uid
            ).all()
        }
        salida = []
        for sid in ids:
            ev = propias.get(sid)
            puede = (
                ev is not None
                and ev.status == "REJECTED"
                and intentos.get(sid, 0) < MAX_INTENTOS
                and ahora < slots[sid].ends_at
                and recompensas.get(sid) is None
            )
            salida.append({
                "boncheRetoId": sid,
                "submitted": ev is not None,
                "evidenceStatus": ev.status if ev is not None else None,
                "reward": recompensas.get(sid),
                "submittedCount": int(conteo.get(sid, 0)),
                "attempts": intentos.get(sid, 0),
                "canRetry": bool(puede),
            })
        return salida

    # --------------------------------------------------------------- ranking

    @app.get("/api/bonches/{bonche_id}/ranking")
    def ranking_bonche(
        bonche_id: str,
        periodo: str = "weekly",
        yo: UsuarioModel = Depends(usuario_actual),
        db=Depends(get_db),
    ):
        uid = yo.id
        if periodo not in ("weekly", "monthly"):
            raise HTTPException(status_code=400, detail="Periodo no v\u00e1lido.")
        b = db.query(BoncheModel).filter(BoncheModel.id == bonche_id).first()
        if b is None:
            raise HTTPException(status_code=404, detail="Bonche no encontrado.")
        if not es_miembro(db, bonche_id, uid):
            raise HTTPException(status_code=403, detail="No perteneces a este bonche.")
        finalizar_pendientes(db, uid)

        offset = timedelta(minutes=b.tz_offset if b.tz_offset is not None else OFFSET_POR_DEFECTO)
        ahora = ahora_utc()
        ahora_local = ahora + offset
        miembros = [
            (m[0], m[1], m[2]) for m in db.query(
                IntegranteBoncheModel.usuario_id,
                UsuarioModel.display_name,
                IntegranteBoncheModel.joined_at,
            )
            .join(UsuarioModel, UsuarioModel.id == IntegranteBoncheModel.usuario_id)
            .filter(IntegranteBoncheModel.bonche_id == bonche_id)
            .all()
        ]

        ini, fin = rango_periodo(ahora_local, periodo)
        filas = filas_periodo(db, bonche_id, ini, fin, offset)
        tabla = clasificar(miembros, filas)

        if periodo == "weekly":
            etiquetas = ["L", "M", "X", "J", "V", "S", "D"]
            hoy = ahora_local.weekday()
            cubeta = lambda dt: dt.weekday()
        else:
            dias = calendar.monthrange(ini.year, ini.month)[1]
            n = (dias + 6) // 7
            etiquetas = [f"S{i + 1}" for i in range(n)]
            hoy = min((ahora_local.day - 1) // 7, n - 1)
            cubeta = lambda dt: min((dt.day - 1) // 7, n - 1)

        por_usuario = [0] * len(etiquetas)
        por_grupo = [0] * len(etiquetas)
        for u, puntos, empieza in filas:
            idx = cubeta(empieza + offset)
            por_grupo[idx] += puntos or 0
            if u == uid:
                por_usuario[idx] += puntos or 0
        n_miembros = max(len(miembros), 1)
        serie_usuario = []
        serie_grupo = []
        acum_u = 0
        acum_g = 0
        for i in range(hoy + 1):
            acum_u += por_usuario[i]
            acum_g += por_grupo[i]
            serie_usuario.append(acum_u)
            serie_grupo.append(round(acum_g / n_miembros, 1))

        historial = []
        rango = range(1, 5) if periodo == "weekly" else range(1, 4)
        for k in rango:
            i2, f2 = rango_periodo(ahora_local, periodo, k)
            fl = filas_periodo(db, bonche_id, i2, f2, offset)
            if not any((x or 0) > 0 for _, x, _ in fl):
                continue
            t2 = clasificar(miembros, fl)
            puesto = next((f["rank"] for f in t2 if f["userId"] == uid), len(t2))
            mio = next((f["xp"] for f in t2 if f["userId"] == uid), 0)
            historial.append({
                "label": etiqueta_periodo(periodo, i2, f2).replace("Semana del", "Sem."),
                "winnerId": t2[0]["userId"],
                "userRank": puesto,
                "userXp": mio,
            })

        fin_corte = min(fin - offset, ahora)
        total = db.query(func.count(BoncheRetoModel.id)).filter(
            BoncheRetoModel.bonche_id == bonche_id,
            BoncheRetoModel.starts_at >= ini - offset,
            BoncheRetoModel.starts_at < fin_corte,
        ).scalar() or 0

        if periodo == "weekly":
            cierre = f"Cierra el lunes {fin.day}/{fin.month}"
        else:
            cierre = f"Cierra el {fin.day}/{fin.month}"

        return {
            "period": periodo,
            "label": etiqueta_periodo(periodo, ini, fin),
            "resetLabel": cierre,
            "entries": tabla,
            "totalChallenges": int(total),
            "chartLabels": etiquetas,
            "userSeries": serie_usuario,
            "groupSeries": serie_grupo,
            "history": historial,
        }

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
            raise HTTPException(status_code=400, detail="Identificador de compra inv\u00e1lido.")
        item = db.query(TiendaItemModel).filter(TiendaItemModel.id == data.item_id).first()
        if item is None or not item.activo:
            raise HTTPException(status_code=404, detail="Ese art\u00edculo no existe.")

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
                raise HTTPException(status_code=402, detail="No te alcanzan las Barras.")
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
                raise HTTPException(status_code=409, detail="Ya tienes este art\u00edculo.")
            raise HTTPException(status_code=409, detail="No pudimos completar la compra. Int\u00e9ntalo de nuevo.")

        return respuesta_compra(db, uid, item, False)