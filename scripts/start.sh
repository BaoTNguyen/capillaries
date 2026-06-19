#!/usr/bin/env bash
# Start the prompt-search service in a detached tmux session.
#
# Usage:
#   ./scripts/start.sh          # start (no-op if already running)
#   ./scripts/start.sh restart  # kill and restart
#   ./scripts/start.sh stop     # kill session
#   ./scripts/start.sh logs     # attach to session (Ctrl+B D to detach)
#   ./scripts/start.sh status   # check if running

set -euo pipefail

SESSION="prompt-search"
PORT=8000
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cmd="${1:-start}"

case "$cmd" in
  stop)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      tmux kill-session -t "$SESSION"
      echo "Stopped."
    else
      echo "Not running."
    fi
    ;;

  restart)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      tmux kill-session -t "$SESSION"
    fi
    exec "$0" start
    ;;

  logs)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "Attaching (Ctrl+B D to detach)..."
      tmux attach-session -t "$SESSION"
    else
      echo "Service is not running. Start it with: ./scripts/start.sh"
      exit 1
    fi
    ;;

  status)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      # Quick HTTP check
      if curl -sf "http://127.0.0.1:${PORT}/health" | grep -q 'true'; then
        echo "Running and ready on http://127.0.0.1:${PORT}"
      else
        echo "Session exists but service not yet ready (still loading models?)"
      fi
    else
      echo "Not running."
    fi
    ;;

  start)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "Already running. Use './scripts/start.sh logs' to attach."
      exit 0
    fi

    tmux new-session -d -s "$SESSION" \
      -x 220 -y 50 \
      "cd '$PROJECT_DIR' && \
       PYTHONPATH='$PROJECT_DIR/src' \
       uvicorn capillaries.server:app \
         --host 127.0.0.1 \
         --port $PORT \
         --log-level info; \
       echo 'Service exited. Press Enter to close.'; read"

    # Wait for ready (up to 30s)
    echo -n "Starting prompt-search service"
    for i in $(seq 1 30); do
      sleep 1
      echo -n "."
      if curl -sf "http://127.0.0.1:${PORT}/health" 2>/dev/null | grep -q 'true'; then
        echo ""
        echo "Ready on http://127.0.0.1:${PORT}"
        echo "  Attach : ./scripts/start.sh logs"
        echo "  Stop   : ./scripts/start.sh stop"
        echo "  Status : ./scripts/start.sh status"
        exit 0
      fi
    done

    echo ""
    echo "Still loading (models take ~10s). Check status with: ./scripts/start.sh status"
    ;;

  *)
    echo "Usage: $0 {start|stop|restart|logs|status}"
    exit 1
    ;;
esac
