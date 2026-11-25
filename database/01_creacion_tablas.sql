-- LA RECOCHA
-- Esquema de base de datos MySQL
-- Generado desde los modelos SQLAlchemy del proyecto
-- Ejecutar sobre una base de datos vacia.

SET NAMES utf8mb4;

CREATE TABLE retos (
	id VARCHAR(50) NOT NULL, 
	title VARCHAR(150) NOT NULL, 
	objective TEXT NOT NULL, 
	description TEXT NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	difficulty VARCHAR(50) NOT NULL, 
	evidence_type VARCHAR(50) NOT NULL, 
	points INTEGER, 
	xp_reward INTEGER, 
	coin_reward INTEGER, 
	starts_at DATETIME NOT NULL, 
	ends_at DATETIME NOT NULL, 
	completed_by INTEGER, 
	total_members INTEGER, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_retos_id ON retos (id);

CREATE TABLE tienda_items (
	id VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	price INTEGER NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	icon VARCHAR(50), 
	one_time BOOL, 
	activo BOOL, 
	PRIMARY KEY (id)
);

CREATE TABLE usuarios (
	id VARCHAR(50) NOT NULL, 
	display_name VARCHAR(100) NOT NULL, 
	email VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255), 
	xp INTEGER, 
	coins INTEGER, 
	streak INTEGER, 
	best_streak INTEGER, 
	completed_challenges INTEGER, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_usuarios_email ON usuarios (email);
CREATE INDEX ix_usuarios_id ON usuarios (id);

CREATE TABLE bonches (
	id VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	invite_code VARCHAR(20) NOT NULL, 
	leader_id VARCHAR(50) NOT NULL, 
	challenges_per_day INTEGER, 
	window_minutes INTEGER, 
	schedule_times VARCHAR(100), 
	tz_offset INTEGER, 
	configured BOOL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(leader_id) REFERENCES usuarios (id)
);
CREATE INDEX ix_bonches_id ON bonches (id);
CREATE UNIQUE INDEX ix_bonches_invite_code ON bonches (invite_code);

CREATE TABLE compras (
	id VARCHAR(60) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	item_id VARCHAR(50) NOT NULL, 
	price INTEGER NOT NULL, 
	request_id VARCHAR(80) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_compra_usuario_request UNIQUE (usuario_id, request_id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id), 
	FOREIGN KEY(item_id) REFERENCES tienda_items (id)
);
CREATE INDEX ix_compras_usuario_id ON compras (usuario_id);

CREATE TABLE dispositivos_push (
	id VARCHAR(64) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	token TEXT NOT NULL, 
	plataforma VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);
CREATE INDEX ix_dispositivos_push_usuario_id ON dispositivos_push (usuario_id);

CREATE TABLE inventario (
	id VARCHAR(120) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	item_id VARCHAR(50) NOT NULL, 
	cantidad INTEGER, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_inventario_usuario_item UNIQUE (usuario_id, item_id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id), 
	FOREIGN KEY(item_id) REFERENCES tienda_items (id)
);
CREATE INDEX ix_inventario_usuario_id ON inventario (usuario_id);

CREATE TABLE participacion_votaciones (
	id VARCHAR(50) NOT NULL, 
	reto_id VARCHAR(50) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	status VARCHAR(30), 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_reto_usuario_participacion UNIQUE (reto_id, usuario_id), 
	FOREIGN KEY(reto_id) REFERENCES retos (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);
CREATE INDEX ix_participacion_votaciones_id ON participacion_votaciones (id);

CREATE TABLE bonche_retos (
	id VARCHAR(120) NOT NULL, 
	bonche_id VARCHAR(50) NOT NULL, 
	reto_id VARCHAR(50) NOT NULL, 
	fecha VARCHAR(10) NOT NULL, 
	slot INTEGER NOT NULL, 
	starts_at DATETIME NOT NULL, 
	ends_at DATETIME NOT NULL, 
	closed_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_bonche_fecha_slot UNIQUE (bonche_id, fecha, slot), 
	FOREIGN KEY(bonche_id) REFERENCES bonches (id), 
	FOREIGN KEY(reto_id) REFERENCES retos (id)
);
CREATE INDEX ix_bonche_retos_bonche_id ON bonche_retos (bonche_id);
CREATE INDEX ix_bonche_retos_id ON bonche_retos (id);

CREATE TABLE integrantes_bonche (
	id VARCHAR(50) NOT NULL, 
	bonche_id VARCHAR(50) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	`role` VARCHAR(20), 
	joined_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_bonche_usuario UNIQUE (bonche_id, usuario_id), 
	FOREIGN KEY(bonche_id) REFERENCES bonches (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);
CREATE INDEX ix_integrantes_bonche_id ON integrantes_bonche (id);

CREATE TABLE notificaciones (
	id VARCHAR(120) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	bonche_id VARCHAR(50), 
	tipo VARCHAR(40) NOT NULL, 
	titulo VARCHAR(150) NOT NULL, 
	mensaje TEXT, 
	ref_tipo VARCHAR(30), 
	ref_id VARCHAR(120), 
	clave VARCHAR(160) NOT NULL, 
	leida BOOL NOT NULL, 
	leida_at DATETIME, 
	created_at DATETIME NOT NULL, 
	push_estado VARCHAR(20) NOT NULL, 
	push_enviada_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_notificacion_usuario_clave UNIQUE (usuario_id, clave), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id), 
	FOREIGN KEY(bonche_id) REFERENCES bonches (id)
);
CREATE INDEX ix_notificaciones_bonche_id ON notificaciones (bonche_id);
CREATE INDEX ix_notificaciones_usuario_id ON notificaciones (usuario_id);

CREATE TABLE evidencias (
	id VARCHAR(50) NOT NULL, 
	reto_id VARCHAR(50) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	image_url TEXT NOT NULL, 
	status VARCHAR(30), 
	submitted_at DATETIME NOT NULL, 
	bonche_reto_id VARCHAR(120), 
	attempt INTEGER NOT NULL, 
	cloudinary_public_id VARCHAR(255), 
	file_deleted_at DATETIME, 
	approval_percentage INTEGER, 
	positive_votes INTEGER, 
	negative_votes INTEGER, 
	rewards_processed BOOL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(reto_id) REFERENCES retos (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id), 
	FOREIGN KEY(bonche_reto_id) REFERENCES bonche_retos (id)
);
CREATE INDEX ix_evidencias_id ON evidencias (id);

CREATE TABLE recompensas (
	id VARCHAR(120) NOT NULL, 
	bonche_reto_id VARCHAR(120) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	evidencia_id VARCHAR(50), 
	estado VARCHAR(20) NOT NULL, 
	xp INTEGER, 
	coins INTEGER, 
	visto BOOL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_recompensa_slot_usuario UNIQUE (bonche_reto_id, usuario_id), 
	FOREIGN KEY(bonche_reto_id) REFERENCES bonche_retos (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);
CREATE INDEX ix_recompensas_bonche_reto_id ON recompensas (bonche_reto_id);
CREATE INDEX ix_recompensas_usuario_id ON recompensas (usuario_id);

CREATE TABLE votaciones (
	id VARCHAR(50) NOT NULL, 
	evidencia_id VARCHAR(50) NOT NULL, 
	usuario_id VARCHAR(50) NOT NULL, 
	decision BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_evidencia_usuario_voto UNIQUE (evidencia_id, usuario_id), 
	FOREIGN KEY(evidencia_id) REFERENCES evidencias (id), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id)
);
CREATE INDEX ix_votaciones_id ON votaciones (id);
