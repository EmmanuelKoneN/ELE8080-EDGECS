#!/usr/bin/env python3
"""Prepare local TLS credentials without printing the registration token."""
import argparse
from common.lab import prepare_lab

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Master certificate IPv4 SAN")
    args = parser.parse_args()
    settings = prepare_lab(args.host)
    print("Accès du laboratoire prêts dans TestApps/.local (validité : 30 jours à la création).")
    print("Certificat :", settings["cert"])
