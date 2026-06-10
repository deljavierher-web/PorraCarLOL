#!/bin/bash
# Script para gestionar el túnel seguro de localhost.run para PorraCarLOL

PORT=5001
PID_FILE="/Users/javidel/.porracarlol_tunnel.pid"
LOG_OUT="/Users/javidel/tunnel_stdout.log"
LOG_ERR="/Users/javidel/tunnel_stderr.log"

kill_existing_tunnels() {
  # Mata cualquier proceso de SSH que esté usando localhost.run en el puerto 5001
  pkill -f "ssh.*localhost.run.*$PORT" 2>/dev/null
}

check_running() {
  if [ -f "$PID_FILE" ]; then
    local pid=$(cat "$PID_FILE")
    # Verificar si el PID guardado realmente existe y sigue activo
    if kill -0 "$pid" 2>/dev/null; then
      return 0 # Está corriendo
    fi
  fi
  # Comprobación de seguridad adicional
  if pgrep -f "ssh.*localhost.run.*$PORT" >/dev/null; then
    return 0 # Está corriendo
  fi
  return 1 # No está corriendo
}

run_tunnel_loop() {
  # Bucle principal que mantiene el túnel activo con límites de reintentos
  local consecutive_failures=0
  local max_failures=5
  
  echo "🚀 Iniciando bucle seguro de localhost.run en el puerto $PORT (PID: $$)..." > "$LOG_OUT"
  
  while true; do
    echo "📡 Intentando conectar túnel..." >> "$LOG_OUT"
    
    # Limpiar cualquier proceso previo que pudiera haber quedado colgado
    kill_existing_tunnels
    
    # Crear archivo temporal para leer la URL asignada
    local tmp_out=$(mktemp)
    
    # Ejecutamos localhost.run en segundo plano usando SSH
    ssh -R 80:localhost:$PORT -o StrictHostKeyChecking=no -o ServerAliveInterval=30 nokey@localhost.run > "$tmp_out" 2>&1 &
    local ssh_pid=$!
    
    # Esperamos hasta 10 segundos para capturar la URL
    local found=false
    local url_assigned=""
    for i in {1..10}; do
      sleep 1
      # Verificar si el proceso ssh se cayó
      if ! kill -0 $ssh_pid 2>/dev/null; then
        break
      fi
      # Buscar la URL https en la salida
      if grep -q "https://" "$tmp_out"; then
        url_assigned=$(grep -o "https://[a-zA-Z0-9.]*\.lhr\.life" "$tmp_out" | head -n 1)
        if [ -n "$url_assigned" ]; then
          found=true
          break
        fi
      fi
    done
    
    # Limpiamos y guardamos salida de error si la hubiera
    cat "$tmp_out" >> "$LOG_ERR"
    rm -f "$tmp_out"
    
    if [ "$found" = true ]; then
      echo "✅ Túnel establecido correctamente: $url_assigned" >> "$LOG_OUT"
      consecutive_failures=0 # Reseteamos el contador de fallos
      
      # Esperamos a que SSH termine naturalmente (caída de conexión, etc.)
      wait $ssh_pid 2>/dev/null
      echo "⚠️ Conexión de localhost.run perdida." >> "$LOG_OUT"
    else
      echo "❌ Error al iniciar el túnel." >> "$LOG_OUT"
      # Nos aseguramos de matar el proceso recién lanzado y sus hijos
      kill -9 $ssh_pid 2>/dev/null
      wait $ssh_pid 2>/dev/null
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
  
  # Esperar unos segundos para verificar si levanta y mostrar la URL al usuario
  echo -n "⏳ Iniciando el túnel de forma segura..."
  local url=""
  for i in {1..8}; do
    sleep 1
    if grep -q "establecido correctamente" "$LOG_OUT" 2>/dev/null; then
      url=$(grep "establecido correctamente" "$LOG_OUT" | head -n 1 | grep -o "https://[a-zA-Z0-9.]*\.lhr\.life")
      break
    fi
    if ! kill -0 "$runner_pid" 2>/dev/null; then
      break
    fi
  done
  echo ""
  
  if check_running && [ -n "$url" ]; then
    echo "✅ ¡Túnel iniciado con éxito!"
    echo "🔗 URL: $url"
  elif check_running; then
    echo "✅ ¡Túnel iniciado! (Esperando asignación de URL. Revisa el comando status)."
  else
    echo "❌ Error al iniciar el túnel. Revisa los logs en: $LOG_OUT y $LOG_ERR"
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
  
  # Limpiar de raíz cualquier proceso de SSH
  kill_existing_tunnels
  echo "✅ Túnel detenido y procesos limpiados correctamente."
}

show_status() {
  if check_running; then
    local pid=""
    [ -f "$PID_FILE" ] && pid=$(cat "$PID_FILE")
    echo "🟢 ESTADO: El túnel está ACTIVO."
    [ -n "$pid" ] && echo "📌 PID del gestor: $pid"
    
    # Mostrar la URL actual si está en los logs
    local url=$(grep "establecido correctamente" "$LOG_OUT" | tail -n 1 | grep -o "https://[a-zA-Z0-9.]*\.lhr\.life")
    [ -n "$url" ] && echo "🔗 URL actual: $url"
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
