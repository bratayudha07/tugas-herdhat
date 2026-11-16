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

DEPLOYMENT_PATH = Path(
    os.getenv("EHR_DEPLOYMENT_PATH", str(ROOT_DIR / "deployment.json"))
)
if not DEPLOYMENT_PATH.is_absolute():
    DEPLOYMENT_PATH = ROOT_DIR / DEPLOYMENT_PATH

# ABI hasil kompilasi. Di lokal dibaca dari artifact Hardhat (selalu segar);
# di hosting `artifacts/` tidak ikut ter-deploy, jadi ada salinan kecil
# `web/abi.json` yang di-commit (dibuat oleh `npm run abi`).
ABI_PATH = (
    ROOT_DIR
    / "artifacts"
    / "contracts"
    / "EHRTraceability.sol"
    / "EHRTraceability.json"
)
ABI_FALLBACK_PATH = WEB_DIR / "abi.json"

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
    """ABI dari artifact Hardhat, atau salinan `web/abi.json` di hosting."""
    artifact = _read_json(ABI_PATH)
    if artifact.get("abi"):
        return artifact["abi"]
    return _read_json(ABI_FALLBACK_PATH) or []


def contract_address() -> str:
    """Alamat kontrak hasil deploy, string kosong kalau belum ada."""
    return str(load_deployment().get("address", "") or "")


def chain_id() -> int | None:
    """Chain ID yang diharapkan, diambil dari `deployment.json`."""
    value = load_deployment().get("chainId")
    return int(value) if value is not None else None


def network_name() -> str:
    return str(load_deployment().get("network", "") or "")


# Nama jaringan yang enak dibaca manusia, dipakai chip topbar, banner MetaMask,
# dan label di halaman Wallet. Jaringan lain dirapikan otomatis ("sepolia" →
# "Sepolia") supaya tidak perlu daftar manual setiap kali pindah jaringan.
_NETWORK_LABELS = {
    "localhost": "Hardhat Local",
    "hardhat": "Hardhat Local",
    "sepolia": "Sepolia",
    "mainnet": "Ethereum",
    "base": "Base",
    "base-sepolia": "Base Sepolia",
    "arbitrum-sepolia": "Arbitrum Sepolia",
}


def network_label() -> str:
    """Nama jaringan untuk ditampilkan ke pengguna."""
    raw = network_name().strip()
    if not raw:
        return "Hardhat Local"
    return _NETWORK_LABELS.get(raw.lower(), raw.replace("-", " ").title())


# Jaringan yang dianggap lokal: tidak ada nilai nyata, akun demo bisa memakai
# kunci bawaan Hardhat yang sudah publik sejak dulu.
LOCAL_NETWORKS = {"localhost", "hardhat", "hardhat-in-process"}


def is_public_network() -> bool:
    """True kalau app menunjuk testnet/mainnet, bukan node lokal."""
    return bool(network_name()) and network_name().lower() not in LOCAL_NETWORKS


def demo_keys() -> dict:
    """Private key akun demo — hanya ada di file deployment jaringan publik.

    Isinya **sengaja** ada di repo: halaman Wallet menampilkannya supaya
    pengunjung bisa mengimpor akun demo ke MetaMask dan mencoba tombol tulis.
    Ini hanya untuk testnet; pola ini tidak boleh dipakai untuk mainnet.
    """
    return dict(load_deployment().get("demoKeys", {}) or {})


def reload() -> None:
    """Lupakan cache file (dipakai setelah deploy ulang)."""
    load_deployment.cache_clear()
    load_abi.cache_clear()


# mtime terakhir file yang dibaca. Deploy ulang menulis `deployment.json`,
# dan alamat kontraknya ikut berubah — kalau cache tidak dibuang, UI akan
# diam-diam membaca kontrak lama yang datanya beda.
_file_stamps: dict[Path, float] = {}


def _stamp(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def reload_if_changed() -> bool:
    """Buang cache file kalau `deployment.json`/artifact berubah di disk."""
    stamps = {
        DEPLOYMENT_PATH: _stamp(DEPLOYMENT_PATH),
        ABI_PATH: _stamp(ABI_PATH),
    }
    if stamps == _file_stamps:
        return False

    _file_stamps.clear()
    _file_stamps.update(stamps)
    reload()
    return True
