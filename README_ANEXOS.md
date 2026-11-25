# La Recocha (anteriormente ChallengeUs)

## Anexos tecnicos - Entrega final

### Tecnologias

- Flutter y Dart: aplicacion Android y web.
- FastAPI y Python: backend.
- MySQL y SQLAlchemy: almacenamiento.
- Cloudinary: evidencias fotograficas.
- Firebase Cloud Messaging: notificaciones push.
- Render: alojamiento del backend.
- Aiven: alojamiento de MySQL.
- Cloudflare Pages: alojamiento web.
- GitHub Releases: actualizaciones de APK.

### Repositorios

- Frontend: https://github.com/joserico3563-oss/challenge_us
- Backend: https://github.com/joserico3563-oss/challengeus-api
- Aplicacion web: https://la-recocha.pages.dev
- APK: https://github.com/joserico3563-oss/challenge_us/releases/latest

### 1. Instalacion del backend

Requisitos: Python, Git y una instancia MySQL.
Version de Python utilizada durante el desarrollo final: 3.15.1.

    git clone https://github.com/joserico3563-oss/challengeus-api.git
    cd challengeus-api
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt

### 2. Configuracion

Copiar .env.example como .env y completar las variables
con credenciales propias.

Generar una clave JWT segura:

    python -c "import secrets; print(secrets.token_hex(32))"

Para las evidencias fotograficas se requiere Cloudinary.

Las notificaciones push pueden mantenerse desactivadas
con PUSH_ENABLED=0. Para activarlas se requiere un proyecto
Firebase compatible con la aplicacion Android y una cuenta
de servicio configurada mediante GOOGLE_APPLICATION_CREDENTIALS.

No publicar credenciales ni archivos privados de Firebase.

### 3. Base de datos

Crear una base de datos MySQL vacia con codificacion utf8mb4.
Seleccionarla desde un cliente SQL y ejecutar los archivos
en el siguiente orden:

1. database/01_creacion_tablas.sql
2. database/03_catalogo_retos.sql
3. database/04_catalogo_tienda.sql
4. database/02_datos_prueba.sql (opcional)

El esquema contiene 14 tablas con claves primarias,
claves foraneas, indices y restricciones de unicidad.

Los catalogos contienen 21 retos y 7 articulos de tienda.

Los datos de prueba incluyen 3 usuarios, 1 Bonche,
3 evidencias, 6 votaciones y 3 recompensas.

Los scripts estan destinados a una base de datos nueva.
No ejecutarlos sobre la base de datos de produccion.
Las migraciones historicas no son necesarias para este esquema.

### 4. Usuarios de demostracion

- jugador1@example.com
- jugador2@example.com
- jugador3@example.com

Password de demostracion: RecochaDemo2026!

Los usuarios son ficticios y sus passwords se almacenan
mediante hash bcrypt. Las referencias de imagenes son
ilustrativas y no corresponden a fotografias reales.

### 5. Ejecutar el backend

    .venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

Documentacion interactiva de la API:

    http://127.0.0.1:8000/docs

### 6. Frontend

    git clone https://github.com/joserico3563-oss/challenge_us.git
    cd challenge_us
    flutter pub get
    flutter analyze

Para conectar el frontend a una instancia propia del backend
se deben adaptar las direcciones de la API y el proxy web.

Compilacion web:

    flutter build web --release

La version web de produccion utiliza un proxy de Cloudflare
Pages para comunicarse con el backend.

### 7. Actualizaciones Android

La aplicacion consulta GitHub Releases para detectar versiones
posteriores a la instalada.

Cada publicacion debe utilizar un tag apk-N, donde N es
el numero de compilacion, y un archivo La_Recocha.apk.

Las actualizaciones requieren conservar el identificador
de aplicacion y la misma clave de firma Android.

La clave privada de firma no forma parte de los anexos.

### 8. Alcance de la entrega

Los scripts SQL fueron generados desde los modelos y
catalogos del proyecto. Los datos de prueba son sinteticos.

La ejecucion integral de los scripts en una nueva instancia
MySQL queda pendiente de validacion independiente.

La instalacion de actualizaciones Android requiere
confirmacion del usuario mediante el instalador del sistema.
