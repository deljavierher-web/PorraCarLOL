"""
PorraCarLOL — Entry Point
Arranca el servidor de desarrollo Flask.
"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))
