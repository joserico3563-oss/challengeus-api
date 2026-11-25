-- LA RECOCHA - Catalogo original de tienda
SET NAMES utf8mb4;
START TRANSACTION;
INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) VALUES ('double_xp', 'Doble XP', 'Tu próximo reto completado te da el doble de XP.', 90, 'advantage', 'bolt', FALSE, TRUE);
INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) VALUES ('streak_shield', 'Escudo de racha', 'Protege tu racha si un día no alcanzas a completar el reto.', 120, 'advantage', 'shield', FALSE, TRUE);
INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) VALUES ('extra_time', 'Tiempo extra', '30 minutos más en la ventana de un reto.', 60, 'advantage', 'more_time', FALSE, TRUE);
INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) VALUES ('swap_challenge', 'Cambio de reto', 'Cambia un reto que no te guste por otro de su misma dificultad.', 80, 'advantage', 'swap', FALSE, TRUE);
INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) VALUES ('pick_challenge', 'Tú eliges', 'Propón el próximo reto para todo el bonche.', 200, 'reward', 'lightbulb', FALSE, TRUE);
INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) VALUES ('avatar_frame', 'Marco dorado', 'Un marco dorado para tu avatar en el Bonche.', 150, 'reward', 'account_circle', TRUE, TRUE);
INSERT INTO tienda_items (id, name, description, price, kind, icon, one_time, activo) VALUES ('stickers', 'Stickers del bonche', 'Un pack de stickers para la charla del grupo.', 70, 'reward', 'celebration', TRUE, TRUE);
COMMIT;
