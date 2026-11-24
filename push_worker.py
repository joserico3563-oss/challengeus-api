import asyncio
import logging
import os
from datetime import datetime, timedelta

from firebase_admin import messaging

from database import SessionLocal
from crear_bd import BoncheModel, BoncheRetoModel, IntegranteBoncheModel
from modelos_push import DispositivoPushModel
from modelos_larecocha import NotificacionModel
from notificaciones import sincronizar
from larecocha import finalizar_pendientes
from push import enviar_push, iniciar_firebase

log = logging.getLogger("uvicorn.error")


def ejecutar_ciclo(generar_retos, offset_de):
    db = SessionLocal()

    try:
        ahora = datetime.utcnow()

        usuarios = [
            r[0] for r in db.query(
                DispositivoPushModel.usuario_id
            ).distinct().all()
        ]

        if not usuarios:
            return

        bonches = db.query(BoncheModel).join(
            IntegranteBoncheModel,
            IntegranteBoncheModel.bonche_id == BoncheModel.id,
        ).filter(
            IntegranteBoncheModel.usuario_id.in_(usuarios),
            BoncheModel.configured.is_(True),
        ).distinct().all()

        for b in bonches:
            fecha = (
                ahora + timedelta(minutes=offset_de(b))
            ).strftime("%Y-%m-%d")

            existe = db.query(BoncheRetoModel.id).filter(
                BoncheRetoModel.bonche_id == b.id,
                BoncheRetoModel.fecha == fecha,
            ).first()

            if not existe:
                generar_retos(db, b, fecha, ahora)

        db.commit()

        for uid in usuarios:
            try:
                finalizar_pendientes(db, uid)
                sincronizar(db, uid, ahora)

                dispositivos = db.query(
                    DispositivoPushModel
                ).filter_by(usuario_id=uid).all()

                avisos = db.query(NotificacionModel).filter(
                    NotificacionModel.usuario_id == uid,
                    NotificacionModel.push_estado == "NO_ENVIADA",
                ).order_by(
                    NotificacionModel.created_at.desc()
                ).limit(100).all()

                for n in avisos:
                    if (
                        n.created_at < ahora - timedelta(minutes=5)
                        or n.leida
                        or n.tipo == "OTHER"
                    ):
                        n.push_estado = "OMITIDA"
                        db.commit()
                        continue

                    if n.bonche_id and not db.query(
                        IntegranteBoncheModel.id
                    ).filter_by(
                        usuario_id=uid,
                        bonche_id=n.bonche_id,
                    ).first():
                        n.push_estado = "OMITIDA"
                        db.commit()
                        continue

                    enviados = 0

                    for d in dispositivos:
                        actual = db.query(
                            DispositivoPushModel
                        ).filter_by(
                            id=d.id, usuario_id=uid
                        ).first()

                        if actual is None:
                            continue

                        if n.created_at < actual.created_at:
                            continue

                        try:
                            enviar_push(
                                actual.token,
                                n.titulo,
                                n.mensaje or "",
                                n.ref_id,
                            )
                            enviados += 1

                        except messaging.UnregisteredError:
                            db.delete(actual)

                        except Exception as exc:
                            log.warning(
                                "Push error: %s",
                                type(exc).__name__,
                            )

                    if enviados:
                        n.push_estado = "ENVIADA"
                        n.push_enviada_at = datetime.utcnow()

                    db.commit()

            except Exception as exc:
                db.rollback()
                log.warning(
                    "Push usuario error: %s",
                    type(exc).__name__,
                )

    finally:
        db.close()


async def ciclo_push(generar_retos, offset_de):
    while True:
        try:
            await asyncio.to_thread(
                ejecutar_ciclo, generar_retos, offset_de
            )
        except Exception as exc:
            log.warning(
                "Push ciclo error: %s",
                type(exc).__name__,
            )

        await asyncio.sleep(60)


def registrar_worker(app, generar_retos, offset_de):

    @app.on_event("startup")
    async def iniciar_worker():
        if os.getenv("PUSH_ENABLED", "0") != "1":
            return

        try:
            iniciar_firebase()
        except Exception as exc:
            log.warning(
                "Firebase no disponible: %s",
                type(exc).__name__,
            )
            return

        app.state.push_task = asyncio.create_task(
            ciclo_push(generar_retos, offset_de)
        )
        log.info("Worker push iniciado.")

    @app.on_event("shutdown")
    async def detener_worker():
        tarea = getattr(app.state, "push_task", None)

        if tarea:
            tarea.cancel()
            try:
                await tarea
            except asyncio.CancelledError:
                pass
