"""DERMS — maître DNP3. Lancer depuis la racine : python -m derms.main"""
GATEWAY_IP = "127.0.0.1"
GATEWAY_PORT = 20000

def main():
    print(f"DERMS : connexion à la gateway {GATEWAY_IP}:{GATEWAY_PORT} (à implémenter)")

if __name__ == "__main__":
    main()
