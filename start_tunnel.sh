#!/bin/bash
# Script para gestionar el túnel de localtunnel de forma segura para PorraCarLOL

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

PORT=5001
SUBDOMAIN="porracarlol-mundial-2026"
PID_FILE="/Users/javidel/.porracarlol_tunnel.pid"
LOG_OUT="/Users/javidel/tunnel_stdout.log"
LOG_ERR="/Users/javidel/tunnel_stderr.log"

kill_existing_tunnels() {
  # Mata cualquier proceso de localtunnel que esté usando nuestro puerto y subdominio
  # para prevenir procesos huérfanos colgados en el sistema.
  pkill -f "node.*lt.*--port $PORT --subdomain $SUBDOMAIN" 2>/dev/null
}

check_running() {
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    # Verificar si el PID guardado realmente existe y sigue activo
    if kill -0 "$pid" 2>/dev/null; then
      return 0 # Está corriendo
    fi
  fi
  # Comprobación de seguridad adicional en caso de PID huérfano o inconsistencia
  if pgrep -f "node.*lt.*--port $PORT --subdomain $SUBDOMAIN" >/dev/null; then
    return 0 # Está corriendo
  fi
  return 1 # No está corriendo
}

run_tunnel_loop() {
  # Bucle principal que mantiene el túnel activo con límites de reintentos
  local consecutive_failures=0
  local max_failures=5
  
  echo "🚀 Iniciando bucle seguro de localtunnel en el puerto $PORT (PID: $$)..." > "$LOG_OUT"
  
  while true; do
    echo "📡 Intentando conectar túnel..." >> "$LOG_OUT"
    
    # Limpiar cualquier proceso previo que pudiera haber quedado colgado
    kill_existing_tunnels
    
    # Ejecutamos localtunnel en segundo plano, guardando logs directamente
    /opt/homebrew/bin/npx localtunnel --port $PORT --subdomain $SUBDOMAIN >> "$LOG_OUT" 2>> "$LOG_ERR" &
    local lt_pid=$!
    
    # Esperamos 5 segundos para verificar si el proceso sigue vivo
    sleep 5
    if kill -0 $lt_pid 2>/dev/null; then
      echo "✅ Túnel establecido correctamente." >> "$LOG_OUT"
      echo "🔗 URL: https://${SUBDOMAIN}.loca.lt" >> "$LOG_OUT"
      consecutive_failures=0 # Reseteamos el contador de fallos
      
      # Esperamos a que localtunnel termine naturalmente (caída de conexión, etc.)
      wait $lt_pid 2>/dev/null
      echo "⚠️ Conexión de localtunnel perdida." >> "$LOG_OUT"
    else
      echo "❌ Error: el proceso del túnel se cayó inmediatamente o no pudo conectar." >> "$LOG_OUT"
      kill_existing_tunnels
      
      consecutive_failures=$((consecutive_failures + 1))
      echo "⚠️ Fallos consecutivos: $consecutive_failures de $max_failures" >> "$LOG_OUT"
      
      if [ "$consecutive_failures" -ge "$max_failures" ]; then
        echo "🛑 Se alcanzó el límite de reintentos ($max_failures). Abortando para proteger el sistema." >> "$LOG_OUT"
        rm -f "$PID_FILE"
        exit 1
      fi
    fi
    
    echo "⏳ Reintentando conexión en 15 segundos..." >> "$LOG_OUT"
    sleep 15
  done
}

start_tunnel() {
  if check_running; then
    echo "⚠️ El túnel ya está en ejecución."
    exit 0
  fi
  
  # Limpiar logs previos para empezar limpios
  > "$LOG_OUT"
  > "$LOG_ERR"
  
  # Arrancar el bucle del túnel en segundo plano
  run_tunnel_loop &
  local runner_pid=$!
  
  # Guardamos el PID del proceso gestor en el archivo de bloqueo
  echo "$runner_pid" > "$PID_FILE"
  
  # Esperar unos segundos para verificar si el bucle sigue corriendo
  echo -n "⏳ Iniciando el túnel de forma segura..."
  sleep 6
  echo ""
  
  if check_running; then
    echo "✅ ¡Túnel iniciado con éxito!"
    echo "🔗 URL: https://${SUBDOMAIN}.loca.lt"
  else
    echo "❌ Error al iniciar el túnel. Revisa los logs en:"
    echo "   📄 $LOG_OUT"
    echo "   📄 $LOG_ERR"
  fi
}

stop_tunnel() {
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    echo "🛑 Deteniendo el túnel (PID del gestor: $pid)..."
    
    # Matar el bucle principal del script
    kill "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
    
    rm -f "$PID_FILE"
  else
    echo "⚠️ No se encontró archivo PID, deteniendo cualquier proceso suelto del túnel..."
  fi
  
  # Limpiar de raíz cualquier proceso de localtunnel
  kill_existing_tunnels
  echo "✅ Túnel detenido y procesos limpiados correctamente."
}

show_status() {
  if check_running; then
    local pid=""
    [ -f "$PID_FILE" ] && pid=$(cat "$PID_FILE")
    echo "🟢 ESTADO: El túnel está ACTIVO."
    [ -n "$pid" ] && echo "📌 PID del gestor: $pid"
    echo "🔗 URL configurada: https://${SUBDOMAIN}.loca.lt"
  else
    echo "🔴 ESTADO: El túnel está APAGADO."
  fi
}

# Evaluar el comando ingresado
case "$1" in
  start)
    start_tunnel
    ;;
  stop)
    stop_tunnel
    ;;
  status)
    show_status
    ;;
  restart)
    stop_tunnel
    sleep 2
    start_tunnel
    ;;
  *)
    echo "Uso: $0 {start|stop|status|restart}"
    exit 1
    ;;
esac
