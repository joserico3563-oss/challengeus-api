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
    return {"message": "API de ChallengeUs operando al 100% 🚀 (Documento Maestro Vinculante Activo)"}

@app.post("/api/auth/login")
def login_usuario(email: str, db: Session = Depends(get_db)):
    usuario = db.query(UsuarioModel).filter(UsuarioModel.email == email).first()
    if not usuario:
        uid = f"u-{email.split('@')[0]}"
        usuario = UsuarioModel(
            id=uid,
            display_name=email.split('@')[0].capitalize(),
            email=email,
            xp=85,
            coins=120,
            streak=4
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

# --- EVIDENCIAS, VOTACIONES Y CICLO DE VIDA CON REGLAS DE NEGOCIO ESTRICTAS ---

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
    return {"message": "¡Evidencia enviada correctamente para calificación!", "evidenceId": nueva_evidencia.id}

class VotoCreate(BaseModel):
    evidencia_id: str
    usuario_id: str
    decision: bool

@app.post("/api/votes")
def emitir_voto(voto: VotoCreate, db: Session = Depends(get_db)):
    evidencia = db.query(EvidenciaModel).filter(EvidenciaModel.id == voto.evidencia_id).first()
    if not evidencia:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada.")

    if evidencia.usuario_id == voto.usuario_id:
        raise HTTPException(status_code=400, detail="No puedes votar tu propia evidencia.")

    nuevo_voto = VotacionModel(
        id=f"voto-{int(datetime.utcnow().timestamp())}-{voto.usuario_id}",
        evidencia_id=voto.evidencia_id,
        usuario_id=voto.usuario_id,
        decision=voto.decision,
        created_at=datetime.utcnow()
    )
    try:
        db.add(nuevo_voto)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya has emitido un voto para esta evidencia.")

    return {"message": "¡Voto registrado con éxito!"}

@app.get("/api/challenges/{reto_id}/pending-votes/{usuario_id}")
def obtener_evidencias_por_calificar(reto_id: str, usuario_id: str, db: Session = Depends(get_db)):
    """
    Devuelve las evidencias de los compañeros que el usuario está obligado a calificar 
    (excluyendo su propia evidencia y aquellas por las que ya votó).
    """
    evidencias_reto = db.query(EvidenciaModel).filter(EvidenciaModel.reto_id == reto_id).all()
    votos_usuario = db.query(VotacionModel).filter(VotacionModel.usuario_id == usuario_id).all()
    evidencias_votadas_ids = {v.evidencia_id for v in votos_usuario}

    pendientes = []
    for ev in evidencias_reto:
        if ev.usuario_id != usuario_id and ev.id not in evidencias_votadas_ids:
            pendientes.append({
                "evidenceId": ev.id,
                "authorId": ev.usuario_id,
                "imageUrl": ev.image_url,
                "submittedAt": ev.submitted_at.isoformat()
            })
    return pendientes

@app.post("/api/challenges/{reto_id}/process-cycle")
def procesar_cierre_ciclo(reto_id: str, db: Session = Depends(get_db)):
    """
    Proceso idéntico e idempotente de cierre:
    1. Calcula aprobación (>50% con al menos 1 voto).
    2. Comprueba obligatoriedad de voto de cada participante.
    3. Entrega XP y monedas SOLO si la evidencia fue aprobada Y cumplió su obligación de votar.
    4. Simula la eliminación temporal del archivo fotográfico.
    """
    reto = db.query(RetoModel).filter(RetoModel.id == reto_id).first()
    if not reto:
        raise HTTPException(status_code=404, detail="Reto no encontrado.")

    evidencias = db.query(EvidenciaModel).filter(EvidenciaModel.reto_id == reto_id).all()
    
    # Obtener todos los usuarios que enviaron evidencia en este reto
    participantes_ids = [ev.usuario_id for ev in evidencias]
    
    resultados = []

    for ev in evidencias:
        if ev.rewards_processed:
            continue

        votos = db.query(VotacionModel).filter(VotacionModel.evidencia_id == ev.id).all()
        total_votos = len(votos)
        favorables = sum(1 for v in votos if v.decision)
        negativos = total_votos - favorables

        ev.positive_votes = favorables
        ev.negative_votes = negativos

        # Regla de aprobación: > 50% con al menos 1 voto válido
        aprobada = False
        if total_votos > 0:
            porcentaje = (favorables / total_votos) * 100
            ev.approval_percentage = int(porcentaje)
            if porcentaje > 50:
                aprobada = True

        if aprobada:
            ev.status = "APPROVED"
        else:
            ev.status = "REJECTED"

        # Validar cumplimiento de votación obligatoria del autor de la evidencia
        # Debe haber votado por todas las evidencias de sus compañeros elegibles
        compañeros_elegibles = [e for e in evidencias if e.usuario_id != ev.usuario_id]
        votos_emitidos_usuario = db.query(VotacionModel).join(EvidenciaModel).filter(
            VotacionModel.usuario_id == ev.usuario_id,
            EvidenciaModel.reto_id == reto_id
        ).all()
        votos_emitidos_ids = {v.evidencia_id for v in votos_emitidos_usuario}
        
        cumplio_votacion = True
        for comp in compañeros_elegibles:
            if comp.id not in votos_emitidos_ids:
                cumplio_votacion = False
                break

        # Recompensas: Solo si la evidencia fue aprobada Y cumplió su obligación de votar
        recompensas_otorgadas = False
        if aprobada and cumplio_votacion:
            usuario = db.query(UsuarioModel).filter(UsuarioModel.id == ev.usuario_id).first()
            if usuario:
                usuario.completed_challenges += 1
                usuario.xp += reto.xp_reward
                usuario.coins += reto.coin_reward
                recompensas_otorgadas = True

        # Marcar procesamiento y vaciar almacenamiento temporal de la foto
        ev.rewards_processed = True
        ev.image_url = "[CONTENIDO_FOTOGRAFICO_ELIMINADO]"
        ev.file_deleted_at = datetime.utcnow()

        resultados.append({
            "evidenceId": ev.id,
            "userId": ev.usuario_id,
            "status": ev.status,
            "approved": aprobada,
            "votingObligationMet": cumplio_votacion,
            "rewardsAwarded": recompensas_otorgadas
        })

    db.commit()
    return {
        "message": "¡Ciclo procesado con reglas de participación obligatoria y limpieza temporal completadas!",
        "results": resultados
    }