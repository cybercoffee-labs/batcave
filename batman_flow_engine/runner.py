import logging

from engine import run_engine

logger = logging.getLogger("runner")


def main():
    result = run_engine()
    if result.get("status") == "already_running":
        print("Engine already running. Aborting.")
        return

    print("Engine run completed.")
    print(f"Ollama: {result.get('ollama_status', 'UNKNOWN')}")
    dq = result.get("data_quality", {})
    print(f"Data Quality: {dq.get('dq_score', 0):.2%} ({dq.get('status', 'N/A')})")


if __name__ == "__main__":
    main()
