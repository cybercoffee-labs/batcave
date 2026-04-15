import subprocess
import time
import datetime

INTERVAL = 300  # 5 minutos

print("🦇 Batman Live Graph — actualizando cada 5 minutos")
print("   Ctrl+C para detener\n")

while True:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] Corriendo engine...", end=" ", flush=True)

    # Corre el engine
    r1 = subprocess.run(["./.venv/bin/python", "engine.py"], capture_output=True, text=True)
    if r1.returncode == 0:
        print("engine OK ✓", end=" ", flush=True)
    else:
        print("engine ERROR ✗", end=" ", flush=True)

    # Regenera el grafo
    r2 = subprocess.run(["python3", "graph_engine.py"], capture_output=True, text=True)
    if r2.returncode == 0:
        print("grafo OK ✓")
    else:
        print(f"grafo ERROR: {r2.stderr[:100]}")

    print(f"   Próxima actualización en 5 min — [{datetime.datetime.now().strftime('%H:%M:%S')}]")
    time.sleep(INTERVAL)
