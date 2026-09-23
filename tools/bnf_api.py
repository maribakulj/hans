"""Appeler l'API IIIF v3 de la BnF (openapi.bnf.fr) avec le jeton OAuth.

    python tools/bnf_api.py token
    python tools/bnf_api.py get 'https://openapi.bnf.fr/iiif/image/v3/ark:/12148/<ark>/f<n>/full/max/0/default.jpg' sortie.jpg

Les identifiants (Basic, base64) sont dans le trousseau macOS :
    security add-generic-password -U -a marcel -s bnf-openapi-basic -w '<base64>'
Ils ne doivent JAMAIS être écrits dans un dépôt. Le jeton dure 3 600 s ; il
est mis en cache dans le scratchpad et renouvelé quand il expire.

Constaté le 23/09/2026 : image, info.json et manifeste (711 canvases pour
bpt6k10403751) répondent. Aucun lien vers l'OCR dans le manifeste v3
(pas de seeAlso par canvas), et toutes les URL d'annotation ou d'ALTO
devinées rendent 404 : l'ALTO reste sur gallica.bnf.fr
(RequestDigitalElement), avec sa limite de débit.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TOKEN_URL = "https://apimauthpubext.bnf.fr/oauth2/token"
CACHE = Path(os.environ.get("TMPDIR", "/tmp")) / "bnf_token_cache.json"


def basic_credentials() -> str:
    out = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-a",
            "marcel",
            "-s",
            "bnf-openapi-basic",
            "-w",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def token() -> str:
    if CACHE.exists():
        c = json.loads(CACHE.read_text())
        if c.get("expires_at", 0) - time.time() > 60:
            return str(c["access_token"])
    req = urllib.request.Request(
        TOKEN_URL,
        data=b"grant_type=client_credentials",
        headers={"Authorization": f"Basic {basic_credentials()}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    d["expires_at"] = time.time() + int(d.get("expires_in", 3600))
    CACHE.write_text(json.dumps(d))
    os.chmod(CACHE, 0o600)
    return str(d["access_token"])


def get(url: str, out: Path | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token()}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if out:
        out.write_bytes(data)
    return data


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("token", "get"):
        print(__doc__)
        return 1
    if sys.argv[1] == "token":
        print(token()[:24] + "…")
        return 0
    data = get(sys.argv[2], Path(sys.argv[3]) if len(sys.argv) > 3 else None)
    print(f"{len(data)} octets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
