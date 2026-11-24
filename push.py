import hashlib
from datetime import datetime, timezone

from fastapi import Depends
from pydantic import BaseModel, Field
from sqlalchemy.dialects.mysql import insert

from modelos_push import DispositivoPushModel
from notificaciones import sincronizar


class TokenPushIn(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


def registrar_rutas_push(app, usuario_actual, get_db):

    @app.post("/api/push/register")
    def registrar_dispositivo(
        data: TokenPushIn,
        yo=Depends(usuario_actual),
        db=Depends(get_db),
    ):
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        identificador = hashlib.sha256(data.token.encode()).hexdigest()

        existente = db.query(DispositivoPushModel).filter_by(
            id=identificador
        ).first()

        nueva_vinculacion = (
            existente is None or existente.usuario_id != yo.id
        )

        if nueva_vinculacion:
            sincronizar(db, yo.id)
            ahora = datetime.now(timezone.utc).replace(tzinfo=None)

        fecha_vinculacion = (
            ahora if nueva_vinculacion else existente.created_at
        )

        stmt = insert(DispositivoPushModel.__table__).values(
            id=identificador,
            usuario_id=yo.id,
            token=data.token,
            plataforma="android",
            created_at=ahora,
            updated_at=ahora,
        )

        stmt = stmt.on_duplicate_key_update(
            usuario_id=yo.id,
            token=data.token,
            updated_at=ahora,
            created_at=fecha_vinculacion,
        )

        db.execute(stmt)
        db.commit()
        return {"ok": True}

    @app.post("/api/push/unregister")
    def desvincular_dispositivo(
        data: TokenPushIn,
        yo=Depends(usuario_actual),
        db=Depends(get_db),
    ):
        identificador = hashlib.sha256(data.token.encode()).hexdigest()

        db.query(DispositivoPushModel).filter(
            DispositivoPushModel.id == identificador,
            DispositivoPushModel.usuario_id == yo.id,
        ).delete(synchronize_session=False)

        db.commit()
        return {"ok": True}


def iniciar_firebase():
    import firebase_admin

    try:
        return firebase_admin.get_app()
    except ValueError:
        return firebase_admin.initialize_app(
            options={"httpTimeout": 10}
        )


def enviar_push(token, titulo, mensaje, referencia=""):
    from firebase_admin import messaging

    app = iniciar_firebase()

    aviso = messaging.Message(
        token=token,
        notification=messaging.Notification(
            title=titulo,
            body=mensaje,
        ),
        data={
            "refId": str(referencia or ""),
        },
        android=messaging.AndroidConfig(
            priority="high",
            ttl=__import__("datetime").timedelta(minutes=5),
            notification=messaging.AndroidNotification(
                sound="default",
                visibility="private",
            ),
        ),
    )

    return messaging.send(aviso, app=app)
