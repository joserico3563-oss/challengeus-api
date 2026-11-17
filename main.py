import os
import re
import random
import string
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import bcrypt
import jwt
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel

from database import get_db
from crear_bd import (
    UsuarioModel, RetoModel, EvidenciaModel, VotacionModel,
    ParticipacionVotacionModel, BoncheModel, IntegranteBoncheModel,
    BoncheRetoModel,
)

app = FastAPI(title="API ChallengeUs - UTB", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MIN_VENTANA = 60
OFFSET_POR_DEFECTO = -300

JWT_SECRET = os.getenv("JWT_SECRET", "challengeus-super-secret-jwt-key-2026")
JWT_DIAS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
bearer = HTTPBearer(auto_error=False)

def hashear(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verificar(password, hashed):
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False

def crear_token(usuario_id):
    payload = {"sub": usuario_id, "exp": datetime.utcnow() + timedelta(days=JWT_DIAS)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def usuario_actual(cred: HTTPAuthorizationCredentials = Security(bearer), db: Session = Depends(get_db)):
    if cred is None:
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Tu sesión venció. Inicia sesión de nuevo.")
    usuario = db.query(UsuarioModel).filter(UsuarioModel.id == payload.get("sub")).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuario no encontrado.")
    return usuario

def usuario_dict(u):
    return {
        "id": u.id,
        "displayName": u.display_name,
        "email": u.email,
        "xp": u.xp or 0,
        "coins": u.coins or 0,
        "streak": u.streak or 0,
        "bestStreak": u.best_streak or 0,
        "completedChallenges": u.completed_challenges or 0,
    }

def buscar_por_email(db, email):
    return db.query(UsuarioModel).filter(func.lower(UsuarioModel.email) == email).first()

def validar_credenciales(email, password):
    if not EMAIL_RE.match(email):
        return "Correo no válido."
    if len(password) < 6:
        return "La contraseña debe tener mínimo 6 caracteres."
    if len(password.encode()) > 72:
        return "La contraseña es demasiado larga."
    return None

class RegistroIn(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None

class LoginIn(BaseModel):
    email: str
    password: str


@app.get("/")
def read_root():
    return {"message": "API de ChallengeUs operando al 100% con JWT"}


@app.post("/api/auth/register")
def registrar(data: RegistroIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    error = validar_credenciales(email, data.password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    usuario = buscar_por_email(db, email)
    nombre = (data.display_name or "").strip() or email.split("@")[0].capitalize()
    if usuario is None:
        usuario = UsuarioModel(
            id=f"u-{uuid.uuid4().hex[:12]}",
            display_name=nombre[:100],
            email=email,
            password_hash=hashear(data.password),
            xp=0, coins=0, streak=0, best_streak=0, completed_challenges=0,
        )
        db.add(usuario)
    elif not usuario.password_hash:
        usuario.password_hash = hashear(data.password)
    else:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo. Inicia sesión.")
    db.commit()
    db.refresh(usuario)
    return {"token": crear_token(usuario.id), "user": usuario_dict(usuario)}


@app.post("/api/auth/login")
def login_usuario(data: LoginIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    usuario = buscar_por_email(db, email)
    if usuario is None:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    if not usuario.password_hash:
        raise HTTPException(
            status_code=403,
            detail="Esta cuenta es anterior a las contraseñas. Toca «Crear cuenta» con este mismo correo para ponerle una.",
        )
    if not verificar(data.password, usuario.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    return {"token": crear_token(usuario.id), "user": usuario_dict(usuario)}


@app.get("/api/challenges/today")
def obtener_retos_hoy(db: Session = Depends(get_db)):
    retos = db.query(RetoModel).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "objective": r.objective,
            "description": r.description,
            "category": r.category,
            "difficulty": r.difficulty,
            "evidenceType": r.evidence_type,
            "points": r.points,
            "xpReward": r.xp_reward,
            "coinReward": r.coin_reward,
            "startsAt": r.starts_at.isoformat() if r.starts_at else None,
            "endsAt": r.ends_at.isoformat() if r.ends_at else None,
            "completedBy": r.completed_by,
            "totalMembers": r.total_members
        } for r in retos
    ]


@app.get("/api/ranking")
def obtener_ranking(db: Session = Depends(get_db)):
    usuarios = db.query(UsuarioModel).order_by(UsuarioModel.xp.desc()).limit(10).all()
    return [
        {
            "id": u.id,
            "displayName": u.display_name,
            "xp": u.xp,
            "coins": u.coins,
            "streak": u.streak,
            "completedChallenges": u.completed_challenges
        } for u in usuarios
    ]


# --- UTILIDADES DE BONCHE ---

def max_ventana(por_dia):
    return 180 - (por_dia - 2) * 20

def offset_de(b):
    return b.tz_offset if b.tz_offset is not None else OFFSET_POR_DEFECTO

def a_minutos(hhmm):
    h, m = hhmm.strip().split(":")
    h = int(h)
    m = int(m)
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise ValueError("hora fuera de rango")
    return h * 60 + m

def lista_horas(raw):
    return [t for t in (raw or "").split(",") if t]

def validar_config(por_dia, ventana, horas_raw):
    if por_dia < 2 or por_dia > 5:
        return "Elige entre 2 y 5 retos al día.", []
    tope = max_ventana(por_dia)
    if ventana < MIN_VENTANA or ventana > tope:
        return f"Con {por_dia} retos la duración va de 60 min hasta {tope} min.", []
    if len(horas_raw) != por_dia:
        return "Falta la hora de inicio de algún reto.", []
    try:
        minutos = sorted(a_minutos(t) for t in horas_raw)
    except Exception:
        return "Hay una hora con formato inválido.", []
    for i in range(len(minutos) - 1):
        if minutos[i] + ventana > minutos[i + 1]:
            return f"El reto {i + 1} se cruza con el reto {i + 2}. Sepáralos o acorta la duración.", []
    if minutos[-1] + ventana > 1440:
        return "El último reto debe terminar antes de medianoche.", []
    horas = [f"{x // 60:02d}:{x % 60:02d}" for x in minutos]
    return None, horas

def miembros_de_bonche(db, bonche_id):
    filas = (
        db.query(IntegranteBoncheModel, UsuarioModel)
        .join(UsuarioModel, UsuarioModel.id == IntegranteBoncheModel.usuario_id)
        .filter(IntegranteBoncheModel.bonche_id == bonche_id)
        .all()
    )
    return [
        {"id": u.id, "name": u.display_name, "xp": u.xp, "streak": u.streak, "role": i.role}
        for i, u in filas
    ]

def bonche_dict(db, b):
    return {
        "id": b.id,
        "name": b.name,
        "description": b.description,
        "inviteCode": b.invite_code,
        "leaderId": b.leader_id,
        "createdAt": (b.created_at.isoformat() + "Z") if b.created_at else None,
        "members": miembros_de_bonche(db, b.id),
        "challengesPerDay": b.challenges_per_day or 3,
        "windowMinutes": b.window_minutes or 90,
        "times": lista_horas(b.schedule_times),
        "tzOffset": offset_de(b),
        "configured": bool(b.configured),
    }


# --- MÓDULO DE BONCHES ---

class BoncheCreate(BaseModel):
    name: str
    description: str = ""
    leader_id: Optional[str] = None


@app.post("/api/bonches")
def crear_bonche(bonche: BoncheCreate, yo: UsuarioModel = Depends(usuario_actual), db: Session = Depends(get_db)):
    if len(bonche.name.strip()) < 3:
        raise HTTPException(status_code=400, detail="El nombre debe tener al menos 3 letras.")
    invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    bonche_id = f"bonche-{uuid.uuid4().hex[:12]}"

    nuevo_bonche = BoncheModel(
        id=bonche_id,
        name=bonche.name.strip(),
        description=bonche.description,
        invite_code=invite_code,
        leader_id=yo.id,
        created_at=datetime.utcnow(),
        configured=False
    )
    db.add(nuevo_bonche)

    integrante = IntegranteBoncheModel(
        id=f"int-{bonche_id}-{yo.id}",
        bonche_id=bonche_id,
        usuario_id=yo.id,
        role="LEADER",
        joined_at=datetime.utcnow()
    )
    db.add(integrante)
    db.commit()

    return {"message": "¡Bonche creado exitosamente!", "boncheId": bonche_id, "inviteCode": invite_code}


@app.get("/api/bonches/user/{usuario_id}")
def obtener_bonches_usuario(usuario_id: str, yo: UsuarioModel = Depends(usuario_actual), db: Session = Depends(get_db)):
    if usuario_id != yo.id:
        raise HTTPException(status_code=403, detail="No puedes ver los bonches de otra persona.")
    integraciones = db.query(IntegranteBoncheModel).filter(IntegranteBoncheModel.usuario_id == yo.id).all()
    bonches_ids = [i.bonche_id for i in integraciones]
    bonches = db.query(BoncheModel).filter(BoncheModel.id.in_(bonches_ids)).all()
    return [bonche_dict(db, b) for b in bonches]


class JoinBonche(BaseModel):
    invite_code: str
    usuario_id: Optional[str] = None


@app.post("/api/bonches/join")
def unirse_bonche(data: JoinBonche, yo: UsuarioModel = Depends(usuario_actual), db: Session = Depends(get_db)):
    bonche = db.query(BoncheModel).filter(BoncheModel.invite_code == data.invite_code.strip().upper()).first()
    if not bonche:
        raise HTTPException(status_code=404, detail="Código de invitación inválido.")

    nuevo_integrante = IntegranteBoncheModel(
        id=f"int-{bonche.id}-{yo.id}",
        bonche_id=bonche.id,
        usuario_id=yo.id,
        role="MEMBER",
        joined_at=datetime.utcnow()
    )
    try:
        db.add(nuevo_integrante)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya eres integrante de este Bonche.")

    total_integrantes = db.query(IntegranteBoncheModel).filter(IntegranteBoncheModel.bonche_id == bonche.id).count()
    return {"message": "Te has unido al Bonche exitosamente.", "boncheId": bonche.id, "totalMembers": total_integrantes}


# --- CONFIGURACIÓN DEL BONCHE (solo el líder) ---

class BoncheConfig(BaseModel):
    user_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    challenges_per_day: int
    window_minutes: int
    times: List[str]
    tz_offset: int


@app.put("/api/bonches/{bonche_id}/config")
def configurar_bonche(bonche_id: str, data: BoncheConfig, yo: UsuarioModel = Depends(usuario_actual), db: Session = Depends(get_db)):
    b = db.query(BoncheModel).filter(BoncheModel.id == bonche_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Bonche no encontrado.")
    if b.leader_id != yo.id:
        raise HTTPException(status_code=403, detail="Solo el líder puede cambiar la configuración.")

    nombre = data.name.strip()
    if len(nombre) < 3:
        raise HTTPException(status_code=400, detail="El nombre debe tener al menos 3 letras.")
    if data.tz_offset < -840 or data.tz_offset > 840:
        raise HTTPException(status_code=400, detail="Zona horaria inválida.")

    error, horas = validar_config(data.challenges_per_day, data.window_minutes, data.times)
    if error:
        raise HTTPException(status_code=400, detail=error)

    b.name = nombre
    if data.description is not None:
        b.description = data.description.strip()
    b.challenges_per_day = data.challenges_per_day
    b.window_minutes = data.window_minutes
    b.schedule_times = ",".join(horas)
    b.tz_offset = data.tz_offset
    b.configured = True
    db.commit()
    db.refresh(b)
    return bonche_dict(db, b)


# --- RETOS DEL DÍA POR BONCHE (sorteo) ---

def generar_retos_del_dia(db, b, fecha, ahora):
    offset = timedelta(minutes=offset_de(b))
    dia_local = datetime.strptime(fecha, "%Y-%m-%d")
    horas = lista_horas(b.schedule_times)
    ventana = timedelta(minutes=b.window_minutes or 90)
    catalogo = [
        r.id for r in db.query(RetoModel).filter(RetoModel.id.like("cat-%")).order_by(RetoModel.id).all()
    ]
    if not catalogo:
        return []

    rng = random.Random(f"{b.id}-{fecha}")
    usados = []
    for slot, hhmm in enumerate(horas, start=1):
        inicio = dia_local + timedelta(minutes=a_minutos(hhmm)) - offset
        fin = inicio + ventana
        if fin <= ahora:
            continue
        ocupados = set(
            fila[0] for fila in db.query(BoncheRetoModel.reto_id).filter(
                BoncheRetoModel.bonche_id != b.id,
                BoncheRetoModel.starts_at < fin,
                BoncheRetoModel.ends_at > inicio,
            ).all()
        )
        libres = [c for c in catalogo if c not in usados and c not in ocupados]
        if not libres:
            libres = [c for c in catalogo if c not in usados] or catalogo
        elegido = rng.choice(libres)
        usados.append(elegido)
        db.add(BoncheRetoModel(
            id=f"br-{b.id}-{fecha}-{slot}",
            bonche_id=b.id,
            reto_id=elegido,
            fecha=fecha,
            slot=slot,
            starts_at=inicio,
            ends_at=fin,
        ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return (
        db.query(BoncheRetoModel)
        .filter(BoncheRetoModel.bonche_id == b.id, BoncheRetoModel.fecha == fecha)
        .order_by(BoncheRetoModel.slot)
        .all()
    )


@app.get("/api/bonches/{bonche_id}/challenges/today")
def retos_de_hoy_del_bonche(bonche_id: str, yo: UsuarioModel = Depends(usuario_actual), db: Session = Depends(get_db)):
    b = db.query(BoncheModel).filter(BoncheModel.id == bonche_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Bonche no encontrado.")
    
    es_miembro = db.query(IntegranteBoncheModel).filter(
        IntegranteBoncheModel.bonche_id == bonche_id,
        IntegranteBoncheModel.usuario_id == yo.id,
    ).first()
    if not es_miembro:
        raise HTTPException(status_code=403, detail="No perteneces a este bonche.")

    if not b.configured:
        return []

    ahora = datetime.utcnow()
    fecha = (ahora + timedelta(minutes=offset_de(b))).strftime("%Y-%m-%d")
    filas = (
        db.query(BoncheRetoModel)
        .filter(BoncheRetoModel.bonche_id == b.id, BoncheRetoModel.fecha == fecha)
        .order_by(BoncheRetoModel.slot)
        .all()
    )
    if not filas:
        filas = generar_retos_del_dia(db, b, fecha, ahora)
    if not filas:
        return []

    ids = [f.reto_id for f in filas]
    retos = {r.id: r for r in db.query(RetoModel).filter(RetoModel.id.in_(ids)).all()}
    total = db.query(IntegranteBoncheModel).filter(IntegranteBoncheModel.bonche_id == b.id).count()

    salida = []
    for f in filas:
        r = retos.get(f.reto_id)
        if r is None:
            continue
        salida.append({
            "id": f.id,
            "retoId": r.id,
            "slot": f.slot,
            "title": r.title,
            "objective": r.objective,
            "description": r.description,
            "category": r.category,
            "difficulty": r.difficulty,
            "evidenceType": r.evidence_type,
            "points": r.points,
            "xpReward": r.xp_reward,
            "coinReward": r.coin_reward,
            "startsAt": f.starts_at.isoformat() + "Z",
            "endsAt": f.ends_at.isoformat() + "Z",
            "completedBy": 0,
            "totalMembers": total,
        })
    return salida


# --- EVIDENCIAS ---

class EvidenciaCreate(BaseModel):
    reto_id: str
    usuario_id: Optional[str] = None
    image_url: str


@app.post("/api/evidences")
def enviar_evidencia(evidencia: EvidenciaCreate, yo: UsuarioModel = Depends(usuario_actual), db: Session = Depends(get_db)):
    existente = db.query(EvidenciaModel).filter(
        EvidenciaModel.reto_id == evidencia.reto_id,
        EvidenciaModel.usuario_id == yo.id
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya has enviado una evidencia para este reto.")

    nueva_evidencia = EvidenciaModel(
        id=f"ev-{int(datetime.utcnow().timestamp())}",
        reto_id=evidencia.reto_id,
        usuario_id=yo.id,
        image_url=evidencia.image_url,
        status="SUBMITTED",
        submitted_at=datetime.utcnow()
    )
    db.add(nueva_evidencia)
    db.commit()
    return {"message": "¡Evidencia enviada correctamente!", "evidenceId": nueva_evidencia.id}