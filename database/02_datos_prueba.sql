-- LA RECOCHA - Datos ficticios de prueba
-- Ejecutar despues de 01, 03 y 04.
-- Exclusivamente para una base de datos de prueba.
-- Password de demostracion: RecochaDemo2026!
SET NAMES utf8mb4;
START TRANSACTION;

INSERT INTO usuarios (id, display_name, email, password_hash, xp, coins, streak, best_streak, completed_challenges) VALUES ('demo-u1', 'Jugador 1', 'jugador1@example.com', '$2b$12$YVgpQw5MHuPDAQZRrGNv6OnFfL4.ncSpIwX9vM8HcrbiLvZJ05PeO', 40, 25, 1, 1, 1);
INSERT INTO usuarios (id, display_name, email, password_hash, xp, coins, streak, best_streak, completed_challenges) VALUES ('demo-u2', 'Jugador 2', 'jugador2@example.com', '$2b$12$YVgpQw5MHuPDAQZRrGNv6OnFfL4.ncSpIwX9vM8HcrbiLvZJ05PeO', 40, 25, 1, 1, 1);
INSERT INTO usuarios (id, display_name, email, password_hash, xp, coins, streak, best_streak, completed_challenges) VALUES ('demo-u3', 'Jugador 3', 'jugador3@example.com', '$2b$12$YVgpQw5MHuPDAQZRrGNv6OnFfL4.ncSpIwX9vM8HcrbiLvZJ05PeO', 40, 25, 1, 1, 1);

INSERT INTO bonches
(id, name, description, invite_code, leader_id,
 challenges_per_day, window_minutes, schedule_times,
 tz_offset, configured, created_at)
VALUES
('demo-b1', 'Bonche de prueba', 'Grupo ficticio',
 'DEMO2026', 'demo-u1', 3, 90,
 '10:00,15:30,20:00', -300, TRUE,
 '2026-11-20 14:00:00');

INSERT INTO integrantes_bonche (id, bonche_id, usuario_id, role, joined_at) VALUES ('demo-m1', 'demo-b1', 'demo-u1', 'LEADER', '2026-11-20 14:00:00');
INSERT INTO integrantes_bonche (id, bonche_id, usuario_id, role, joined_at) VALUES ('demo-m2', 'demo-b1', 'demo-u2', 'MEMBER', '2026-11-20 14:00:00');
INSERT INTO integrantes_bonche (id, bonche_id, usuario_id, role, joined_at) VALUES ('demo-m3', 'demo-b1', 'demo-u3', 'MEMBER', '2026-11-20 14:00:00');

INSERT INTO bonche_retos
(id, bonche_id, reto_id, fecha, slot,
 starts_at, ends_at, closed_at)
VALUES
('demo-br1', 'demo-b1', 'cat-01', '2026-11-20', 0,
 '2026-11-20 15:00:00', '2026-11-20 16:30:00',
 '2026-11-20 16:00:00');

INSERT INTO evidencias (id, reto_id, usuario_id, image_url, status, submitted_at, bonche_reto_id, attempt, file_deleted_at, approval_percentage, positive_votes, negative_votes, rewards_processed) VALUES ('demo-e1', 'cat-01', 'demo-u1', 'https://example.com/evidencia1.jpg', 'APPROVED', '2026-11-20 15:20:00', 'demo-br1', 1, '2026-11-20 16:00:00', 100, 2, 0, TRUE);
INSERT INTO evidencias (id, reto_id, usuario_id, image_url, status, submitted_at, bonche_reto_id, attempt, file_deleted_at, approval_percentage, positive_votes, negative_votes, rewards_processed) VALUES ('demo-e2', 'cat-01', 'demo-u2', 'https://example.com/evidencia2.jpg', 'APPROVED', '2026-11-20 15:20:00', 'demo-br1', 1, '2026-11-20 16:00:00', 100, 2, 0, TRUE);
INSERT INTO evidencias (id, reto_id, usuario_id, image_url, status, submitted_at, bonche_reto_id, attempt, file_deleted_at, approval_percentage, positive_votes, negative_votes, rewards_processed) VALUES ('demo-e3', 'cat-01', 'demo-u3', 'https://example.com/evidencia3.jpg', 'APPROVED', '2026-11-20 15:20:00', 'demo-br1', 1, '2026-11-20 16:00:00', 100, 2, 0, TRUE);
INSERT INTO votaciones (id, evidencia_id, usuario_id, decision, created_at) VALUES ('demo-v1-2', 'demo-e1', 'demo-u2', TRUE, '2026-11-20 15:55:00');
INSERT INTO votaciones (id, evidencia_id, usuario_id, decision, created_at) VALUES ('demo-v1-3', 'demo-e1', 'demo-u3', TRUE, '2026-11-20 15:55:00');
INSERT INTO votaciones (id, evidencia_id, usuario_id, decision, created_at) VALUES ('demo-v2-1', 'demo-e2', 'demo-u1', TRUE, '2026-11-20 15:55:00');
INSERT INTO votaciones (id, evidencia_id, usuario_id, decision, created_at) VALUES ('demo-v2-3', 'demo-e2', 'demo-u3', TRUE, '2026-11-20 15:55:00');
INSERT INTO votaciones (id, evidencia_id, usuario_id, decision, created_at) VALUES ('demo-v3-1', 'demo-e3', 'demo-u1', TRUE, '2026-11-20 15:55:00');
INSERT INTO votaciones (id, evidencia_id, usuario_id, decision, created_at) VALUES ('demo-v3-2', 'demo-e3', 'demo-u2', TRUE, '2026-11-20 15:55:00');
INSERT INTO recompensas (id, bonche_reto_id, usuario_id, evidencia_id, estado, xp, coins, visto, created_at) VALUES ('demo-r1', 'demo-br1', 'demo-u1', 'demo-e1', 'PAGADA', 40, 25, TRUE, '2026-11-20 16:00:00');
INSERT INTO recompensas (id, bonche_reto_id, usuario_id, evidencia_id, estado, xp, coins, visto, created_at) VALUES ('demo-r2', 'demo-br1', 'demo-u2', 'demo-e2', 'PAGADA', 40, 25, TRUE, '2026-11-20 16:00:00');
INSERT INTO recompensas (id, bonche_reto_id, usuario_id, evidencia_id, estado, xp, coins, visto, created_at) VALUES ('demo-r3', 'demo-br1', 'demo-u3', 'demo-e3', 'PAGADA', 40, 25, TRUE, '2026-11-20 16:00:00');
COMMIT;
