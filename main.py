import random
import string
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from database import get_db
from crear_bd import (
    UsuarioModel, RetoModel, EvidenciaModel, VotacionModel, 
    ParticipacionVotacionModel, BoncheModel, IntegranteBoncheModel
)

app = FastAPI(title="API ChallengeUs - UTB", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "API de ChallengeUs operando al 100% 🚀 (Modo Solitario Activo)"}

@app.post("/api/auth/login")
def login_usuario(email: str, db: Session = Depends(get_db)):
    usuario = db.query(UsuarioModel).filter(UsuarioModel.email == email).first()
    if not usuario:
        uid = f"u-{email.split('@')[0]}"
        usuario = UsuarioModel(
            id=uid,
            display_name=email.split('@')[0].capitalize(),
            email=email,
            xp=0,
            coins=0,
            streak=0
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
    return {
        "id": usuario.id,
        "displayName": usuario.display_name,
        "email": usuario.email,
        "xp": usuario.xp,
        "coins": usuario.coins,
        "streak": usuario.streak,
        "bestStreak": usuario.best_streak,
        "completedChallenges": usuario.completed_challenges
    }

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

# --- MÓDULO DE BONCHES ---

class BoncheCreate(BaseModel):
    name: str
    description: str = ""
    leader_id: str

@app.post("/api/bonches")
def crear_bonche(bonche: BoncheCreate, db: Session = Depends(get_db)):
    invite_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    bonche_id = f"bonche-{int(datetime.utcnow().timestamp())}"

    nuevo_bonche = BoncheModel(
        id=bonche_id,
        name=bonche.name,
        description=bonche.description,
        invite_code=invite_code,
        leader_id=bonche.leader_id,
        created_at=datetime.utcnow()
    )
    db.add(nuevo_bonche)

    integrante = IntegranteBoncheModel(
        id=f"int-{bonche_id}-{bonche.leader_id}",
        bonche_id=bonche_id,
        usuario_id=bonche.leader_id,
        role="LEADER",
        joined_at=datetime.utcnow()
    )
    db.add(integrante)
    db.commit()

    return {"message": "¡Bonche creado exitosamente! 🛡️", "boncheId": bonche_id, "inviteCode": invite_code}

@app.get("/api/bonches/user/{usuario_id}")
def obtener_bonches_usuario(usuario_id: str, db: Session = Depends(get_db)):
    integraciones = db.query(IntegranteBoncheModel).filter(IntegranteBoncheModel.usuario_id == usuario_id).all()
    bonches_ids = [i.bonche_id for i in integraciones]
    bonches = db.query(BoncheModel).filter(BoncheModel.id.in_(bonches_ids)).all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "inviteCode": b.invite_code,
            "leaderId": b.leader_id
        } for b in bonches
    ]

class JoinBonche(BaseModel):
    invite_code: str
    usuario_id: str

@app.post("/api/bonches/join")
def unirse_bonche(data: JoinBonche, db: Session = Depends(get_db)):
    bonche = db.query(BoncheModel).filter(BoncheModel.invite_code == data.invite_code).first()
    if not bonche:
        raise HTTPException(status_code=404, detail="Código de invitación inválido.")

    nuevo_integrante = IntegranteBoncheModel(
        id=f"int-{bonche.id}-{data.usuario_id}",
        bonche_id=bonche.id,
        usuario_id=data.usuario_id,
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

# --- EVIDENCIAS Y PROCESAMIENTO MODO SOLITARIO ---

class EvidenciaCreate(BaseModel):
    reto_id: str
    usuario_id: str
    image_url: str

@app.post("/api/evidences")
def enviar_evidencia(evidencia: EvidenciaCreate, db: Session = Depends(get_db)):
    existente = db.query(EvidenciaModel).filter(
        EvidenciaModel.reto_id == evidencia.reto_id,
        EvidenciaModel.usuario_id == evidencia.usuario_id
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Ya has enviado una evidencia para este reto.")

    nueva_evidencia = EvidenciaModel(
        id=f"ev-{int(datetime.utcnow().timestamp())}",
        reto_id=evidencia.reto_id,
        usuario_id=evidencia.usuario_id,
        image_url=evidencia.image_url,
        status="SUBMITTED",
        submitted_at=datetime.utcnow()
    )
    db.add(nueva_evidencia)
    db.commit()
    return {"message": "¡Evidencia enviada correctamente!", "evidenceId": nueva_evidencia.id}

@app.post("/api/challenges/{reto_id}/process-cycle")
def procesar_cierre_ciclo(reto_id: str, db: Session = Depends(get_db)):
    reto = db.query(RetoModel).filter(RetoModel.id == reto_id).first()
    if not reto:
        raise HTTPException(status_code=404, detail="Reto no encontrado.")

    evidencias = db.query(EvidenciaModel).filter(EvidenciaModel.reto_id == reto_id).all()
    resultados = []

    for ev in evidencias:
        if ev.rewards_processed:
            continue

        # Modo solitario: aprobación automática si no hay votos externos
        aprobada = True
        usuario = db.query(UsuarioModel).filter(UsuarioModel.id == ev.usuario_id).first()
        recompensas_otorgadas = False
        if usuario:
            usuario.completed_challenges += 1
            usuario.xp += reto.xp_reward
            usuario.coins += reto.coin_reward
            recompensas_otorgadas = True

        ev.rewards_processed = True
        ev.status = "APPROVED"
        ev.image_url = "[CONTENIDO_FOTOGRAFICO_ELIMINADO]"
        ev.file_deleted_at = datetime.utcnow()

        resultados.append({
            "evidenceId": ev.id,
            "userId": ev.usuario_id,
            "status": ev.status,
            "approved": aprobada,
            "rewardsAwarded": recompensas_otorgadas
        })

    db.commit()
    return {"message": "¡Ciclo procesado en modo solitario con éxito!", "results": resultados}