"""Gateway — outstation DNP3. Lancer depuis la racine : python -m gateway.main"""
import sys

ECOUTE_IP = "127.0.0.1"
ECOUTE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20000  # 20001, 20002 pour les autres passerelles

def main():
    print(f"Gateway : écoute DNP3 sur {ECOUTE_IP}:{ECOUTE_PORT} (à implémenter)")

if __name__ == "__main__":
    main()
