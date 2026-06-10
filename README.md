# 🏆 PorraCarLOL — Pronosticador del Torneo

Sistema de porra deportiva gratuita entre amigos, estilo bet365. Pronostica resultados 1X2 de partidos de fútbol, usa tu comodín sabiamente y compite por el primer puesto del ranking.

## 🎯 Características

- **Pronósticos 1X2** con cuotas reales de casas de apuestas
- **Comodín** por jornada: duplica tus puntos si aciertas
- **Rankings** en tiempo real: General y por Jornada
- **Automatización** de cuotas (The Odds API) y resultados (API-Football)
- **Panel Admin** para gestión manual de partidos
- **Interfaz premium** estilo betting app (modo oscuro, animaciones, responsive)

---

## 🚀 Instalación Paso a Paso

### 1. Requisitos Previos

- **Python 3.10+**: [Descargar](https://python.org/downloads/)
- **ngrok** (opcional, para compartir): [Descargar](https://ngrok.com/download)

### 2. Clonar / Descargar el Proyecto

```bash
cd PorraCarLOL
```

### 3. Crear Entorno Virtual

```bash
# Crear entorno virtual
python3 -m venv venv

# Activar entorno virtual
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 4. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 5. Configurar Variables de Entorno

```bash
# Copiar el archivo de ejemplo
cp .env.example .env

# Editar .env con tus claves
nano .env    # o usa tu editor favorito
```

**Variables importantes:**

| Variable | Descripción | Requerida |
|----------|-------------|-----------|
| `FLASK_SECRET_KEY` | Clave secreta de Flask (genera una aleatoria) | ✅ Sí |
| `JWT_SECRET_KEY` | Clave secreta para JWT | ✅ Sí |
| `ADMIN_USERNAME` | Username del admin | ✅ Sí |
| `ADMIN_PASSWORD` | Password del admin | ✅ Sí |
| `ODDS_API_KEY` | [The Odds API](https://the-odds-api.com/) (gratis) | 📡 Para cuotas auto |
| `FOOTBALL_API_KEY` | [API-Football](https://rapidapi.com/api-sports/api/api-football) (gratis) | ⚽ Para resultados auto |

> **Nota**: El sistema funciona perfectamente sin las API keys externas. Puedes crear y gestionar partidos manualmente desde el Panel Admin.

### 6. Arrancar el Servidor

```bash
python run.py
```

Abre tu navegador en **http://localhost:5001** 🎉

---

## 🌐 Compartir con Amigos (ngrok)

Para que tus amigos puedan acceder desde cualquier lugar:

### 1. Instalar ngrok

```bash
# macOS (Homebrew)
brew install ngrok

# O descarga desde https://ngrok.com/download
```

### 2. Crear cuenta gratuita

Regístrate en [ngrok.com](https://ngrok.com/) y copia tu authtoken.

```bash
ngrok config add-authtoken TU_AUTH_TOKEN
```

### 3. Exponer el puerto

```bash
# Con el servidor Flask corriendo en otra terminal:
ngrok http 5001
```

ngrok te dará una URL pública tipo:
```
https://xxxx-xx-xx-xxx-xxx.ngrok-free.app
```

**¡Comparte esa URL con tus amigos!** 📲

> ⚠️ La URL cambia cada vez que reinicias ngrok (plan gratuito).

---

## 📖 Cómo Jugar

1. **Inicia sesión** con el usuario y contraseña que te dé el administrador.
2. Ve a **Mis Pronósticos** y selecciona la jornada
3. Para cada partido, pulsa **1** (gana local), **X** (empate) o **2** (gana visitante)
4. Asigna tu **🃏 Comodín** al partido donde más seguro estés (×2 puntos)
5. Cuando el partido termine, los puntos se calculan automáticamente
6. ¡Mira el **Ranking** para ver quién lidera!

### Sistema de Puntos

| Resultado | Puntos |
|-----------|--------|
| Acierto | Cuota × 10 |
| Acierto + Comodín | Cuota × 10 × 2 |
| Fallo | 0 |

**Ejemplo**: Si la cuota del empate es 3.50 y aciertas con comodín → `3.50 × 10 × 2 = 70 puntos`

---

## ⚙️ Panel de Administración

Accede a `/admin` con la cuenta de administrador para:

- **Crear partidos** manualmente
- **Sincronizar cuotas** desde The Odds API
- **Sincronizar resultados** desde API-Football
- **Finalizar partidos** manualmente (seleccionando 1, X o 2)
- **Ver usuarios** registrados

---

## 🔧 Obtener API Keys (Gratis)

### The Odds API (Cuotas)

1. Ve a [the-odds-api.com](https://the-odds-api.com/)
2. Regístrate con tu email
3. Copia el API key que te envían
4. Pégalo en `.env` → `ODDS_API_KEY=tu-key`
5. **Límite gratuito**: 500 créditos/mes

### API-Football (Resultados)

1. Ve a [RapidAPI](https://rapidapi.com/api-sports/api/api-football)
2. Crea cuenta y suscríbete al plan **Free**
3. Copia tu `X-RapidAPI-Key`
4. Pégalo en `.env` → `FOOTBALL_API_KEY=tu-key`
5. **Límite gratuito**: 100 requests/día

---

## 📁 Estructura del Proyecto

```
PorraCarLOL/
├── app/
│   ├── __init__.py          # Application Factory
│   ├── config.py            # Configuración
│   ├── extensions.py        # SQLAlchemy, JWT, Bcrypt, Scheduler
│   ├── models/              # Modelos: Usuario, Partido, Prediccion
│   ├── routes/              # Endpoints: auth, api, admin
│   ├── services/            # Lógica: scoring, cuotas, resultados
│   └── templates/           # HTML: login, dashboard, pronosticos, admin
├── static/
│   ├── css/styles.css       # Estilos custom
│   └── js/app.js            # JavaScript frontend
├── .env.example             # Variables de entorno (ejemplo)
├── requirements.txt         # Dependencias Python
├── run.py                   # Entry point
└── README.md                # Este archivo
```

---

## 🐛 Troubleshooting

| Problema | Solución |
|----------|----------|
| `ModuleNotFoundError` | Asegúrate de tener el venv activado: `source venv/bin/activate` |
| Puerto 5001 ocupado | Cambia el puerto en `run.py`: `app.run(port=5002)` |
| Error de permisos SQLite | Verifica que la carpeta `instance/` sea escribible |
| API keys no funcionan | Revisa que no haya espacios extra en `.env` |
| ngrok no conecta | Verifica que Flask esté corriendo en otra terminal |

---

## 📝 Licencia

Proyecto personal para uso entre amigos. Sin fines comerciales.

---

Hecho con ❤️ y ☕ para la porra del grupo.
