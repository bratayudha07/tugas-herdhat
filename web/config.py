"""Konfigurasi aplikasi web: path, ABI, alamat kontrak, URL RPC.

Semua path dihitung dari lokasi file ini, jadi server bisa dijalankan dari
direktori mana pun (`uvicorn web.main:app`) tanpa mengubah kode.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
ROOT_DIR = WEB_DIR.parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

DEPLOYMENT_PATH = ROOT_DIR / "deployment.json"
ABI_PATH = (
    ROOT_DIR
    / "artifacts"
    / "contracts"
    / "EHRTraceability.sol"
    / "EHRTraceability.json"
)

# RPC lokal Hardhat. Bisa diarahkan ke jaringan lain lewat env var.
RPC_URL = os.getenv("EHR_RPC_URL", "http://127.0.0.1:8545")

# Cache pembacaan chain: cukup lama supaya refresh halaman tidak menghajar
# RPC, cukup pendek supaya data yang baru ditulis tetap kelihatan.
CACHE_TTL = float(os.getenv("EHR_CACHE_TTL", "15"))

# Timeout per request RPC. Node lokal mati harus cepat ketahuan, bukan
# menggantung halaman.
RPC_TIMEOUT = float(os.getenv("EHR_RPC_TIMEOUT", "3"))


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def load_deployment() -> dict:
    """Isi `deployment.json` (alamat kontrak + akun demo)."""
    return _read_json(DEPLOYMENT_PATH)


@lru_cache(maxsize=1)
def load_abi() -> list:
    """ABI dari artifact Hardhat — satu-satunya sumber kebenaran."""
    artifact = _read_json(ABI_PATH)
    return artifact.get("abi", [])


def contract_address() -> str:
    """Alamat kontrak hasil deploy, string kosong kalau belum ada."""
    return str(load_deployment().get("address", "") or "")


def chain_id() -> int | None:
    """Chain ID yang diharapkan, diambil dari `deployment.json`."""
    value = load_deployment().get("chainId")
    return int(value) if value is not None else None


def network_name() -> str:
    return str(load_deployment().get("network", "") or "")


def reload() -> None:
    """Lupakan cache file (dipakai setelah deploy ulang)."""
    load_deployment.cache_clear()
    load_abi.cache_clear()
