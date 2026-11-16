"""Penghubung Web3.py ke Hardhat node.

Prinsip: server hanya membaca chain. Semua transaksi ditandatangani wallet
di browser (MetaMask), jadi tidak ada private key di proses Python.

Pembacaan di-cache sebentar (`config.CACHE_TTL`) supaya refresh halaman tidak
menembak RPC berulang kali — penting untuk laptop low-spec.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from web3 import Web3

from . import config

_cache: dict[str, tuple[float, Any]] = {}

_w3: Web3 | None = None


def get_web3() -> Web3:
    """Provider HTTP tunggal (dibuat sekali, dipakai ulang)."""
    global _w3
    if _w3 is None:
        _w3 = Web3(
            Web3.HTTPProvider(
                config.RPC_URL,
                request_kwargs={"timeout": config.RPC_TIMEOUT},
            )
        )
    return _w3


def _cached(key: str, factory: Callable[[], Any], ttl: float | None = None) -> Any:
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]

    value = factory()
    _cache[key] = (now + (config.CACHE_TTL if ttl is None else ttl), value)
    return value


def refresh() -> None:
    """Kosongkan cache — dipakai tombol "Muat ulang data".

    Sekalian membaca ulang `deployment.json`: setiap deploy ulang mengubah
    alamat kontrak, dan tanpa ini UI tetap menunjuk kontrak yang lama.
    """
    _cache.clear()
    config.reload_if_changed()


def get_contract():
    """Objek kontrak Web3, atau None kalau alamat/ABI belum siap."""
    address = config.contract_address()
    abi = config.load_abi()
    if not address or not abi:
        return None

    return get_web3().eth.contract(
        address=Web3.to_checksum_address(address),
        abi=abi,
    )


def health() -> dict:
    """Status koneksi + kontrak. Tidak pernah melempar exception.

    Hasilnya di-cache supaya satu halaman tidak menembak RPC berkali-kali.
    Kalau RPC mati, cache-nya pendek (3 detik) agar node yang baru dinyalakan
    cepat terdeteksi tanpa menunggu TTL penuh.
    """
    now = time.monotonic()
    hit = _cache.get("health")
    if hit is not None and hit[0] > now:
        return hit[1]

    info = _probe_health()
    ttl = config.CACHE_TTL if info["rpc"] else 3
    _cache["health"] = (now + ttl, info)
    return info


def _probe_health() -> dict:
    # Deploy ulang menulis deployment.json; cek mtime supaya alamat baru
    # terpakai tanpa harus restart server.
    config.reload_if_changed()

    info: dict[str, Any] = {
        "rpc": False,
        "chainId": None,
        "block": None,
        "contract": False,
        "address": config.contract_address(),
        "expectedChainId": config.chain_id(),
        "rpcUrl": config.RPC_URL,
        "error": None,
    }

    try:
        w3 = get_web3()

        if not w3.is_connected():
            info["error"] = "RPC tidak merespons"
            return info

        info["rpc"] = True
        info["chainId"] = w3.eth.chain_id
        info["block"] = w3.eth.block_number

        address = info["address"]
        if not address:
            info["error"] = "deployment.json belum punya alamat kontrak"
            return info

        code = w3.eth.get_code(Web3.to_checksum_address(address))
        info["contract"] = len(code) > 2
        if not info["contract"]:
            info["error"] = "Tidak ada kontrak di alamat ini"
    except Exception as exc:  # node mati, timeout, alamat tidak valid, dll.
        info["error"] = f"{type(exc).__name__}: {exc}"

    return info


def _read_meta() -> dict:
    """Baca identitas kontrak + jumlah data. Melempar exception ke pemanggil."""
    contract = get_contract()
    if contract is None:
        return {"error": "Kontrak belum siap"}

    return {
        "name": contract.functions.name().call(),
        "symbol": contract.functions.symbol().call(),
        "totalSupply": contract.functions.totalSupply().call(),
        "doctorCount": len(contract.functions.getDoctors().call()),
    }


def contract_meta() -> dict | None:
    """Ringkasan kontrak untuk dashboard; None kalau tidak bisa dibaca."""
    status = health()
    if not (status["rpc"] and status["contract"]):
        return None

    try:
        return _cached("meta", _read_meta)
    except Exception:
        # Jangan bikin halaman 500 gara-gara kontrak beda versi.
        return None


def batch_dict(raw) -> dict:
    """Struct `PatientBatch` → dict. Urutan field mengikuti kontrak."""
    return {
        "tokenId": int(raw[0]),
        "patientId": raw[1],
        "patientName": raw[2],
        "complaint": raw[3],
        "treatment": raw[4],
        "medicine": raw[5],
        "status": int(raw[6]),
        "createdAt": int(raw[7]),
        "createdBy": raw[8],
        "doctor": raw[9],
        "patient": raw[10],
    }


def _read_batches() -> list[dict]:
    """Baca semua batch dari `totalSupply()` + `getBatch()`.

    Sengaja tidak memakai event log: cara ini tetap benar walau node
    di-restart dan tidak perlu indexer.
    """
    contract = get_contract()
    if contract is None:
        raise RuntimeError("Kontrak belum siap")

    total = int(contract.functions.totalSupply().call())
    return [
        batch_dict(contract.functions.getBatch(token_id).call())
        for token_id in range(1, total + 1)
    ]


def list_batches() -> list[dict] | None:
    """Semua batch, atau None kalau chain/kontrak tidak bisa dibaca."""
    status = health()
    if not (status["rpc"] and status["contract"]):
        return None

    try:
        return _cached("batches", _read_batches)
    except Exception:
        return None


def batch_detail(token_id: int) -> dict | None:
    """Satu batch + riwayatnya; None kalau batch tidak ada / RPC mati."""
    contract = get_contract()
    if contract is None:
        return None

    try:
        batch = batch_dict(contract.functions.getBatch(token_id).call())
        history = contract.functions.getHistory(token_id).call()
    except Exception:
        return None

    batch["history"] = [
        {"action": entry[0], "actor": entry[1], "timestamp": int(entry[2])}
        for entry in history
    ]
    return batch


def consent_of(token_id: int, doctor: str) -> bool | None:
    """`consent[tokenId][doctor]` — None kalau tidak bisa dibaca.

    Izin mengatur hak menulis. UI memakainya untuk memutuskan tombol mana
    yang boleh tampil, bukan untuk menyembunyikan data.
    """
    contract = get_contract()
    if contract is None or not doctor:
        return None

    try:
        return bool(
            contract.functions.consent(
                token_id, Web3.to_checksum_address(doctor)
            ).call()
        )
    except Exception:
        return None


def account_info(address: str) -> dict | None:
    """Saldo, nonce, dan harga gas satu alamat — dibaca dari RPC server.

    Halaman Wallet menampilkan angka ini sebagai pembanding independen dari
    MetaMask: kalau wallet tersambung ke jaringan lain, saldo di sini tetap
    angka milik node yang dipakai aplikasi.
    """
    if not address or not Web3.is_address(address):
        return None

    checksum = Web3.to_checksum_address(address)

    def read() -> dict | None:
        try:
            w3 = get_web3()
            return {
                "address": checksum,
                "balance": float(Web3.from_wei(w3.eth.get_balance(checksum), "ether")),
                "nonce": int(w3.eth.get_transaction_count(checksum)),
                "gasPrice": float(Web3.from_wei(w3.eth.gas_price, "gwei")),
            }
        except Exception:
            return None

    # Cache per alamat: pindah akun di MetaMask tidak perlu menembak RPC lagi.
    return _cached(f"account:{checksum.lower()}", read)


def doctors() -> list[str]:
    """Daftar dokter terdaftar untuk dropdown/filter."""
    contract = get_contract()
    if contract is None:
        return []

    try:
        return _cached("doctors", lambda: list(contract.functions.getDoctors().call()))
    except Exception:
        return []


ROLE_NAMES = ["NONE", "RECEPTIONIST", "DOCTOR", "ADMIN"]


def role_of(address: str) -> dict | None:
    """Peran satu alamat menurut `getRole()`. None kalau alamat/RPC bermasalah.

    Peran `NONE` bisa berarti pasien (pemilik NFT) — penyimpulan itu terjadi
    di UI, bukan di sini, karena butuh `ownerOf()` per batch.
    """
    contract = get_contract()
    if contract is None or not address:
        return None

    try:
        checksum = Web3.to_checksum_address(address)
    except ValueError:
        return None

    def read() -> dict:
        value = int(contract.functions.getRole(checksum).call())
        return {
            "address": checksum,
            "role": ROLE_NAMES[value] if 0 <= value < len(ROLE_NAMES) else "NONE",
            "roleIndex": value,
        }

    try:
        # Hanya hasil sukses yang di-cache: kegagalan RPC dibiarkan dicoba
        # ulang pada permintaan berikutnya, bukan disimpan 15 detik.
        return _cached(f"role:{checksum.lower()}", read)
    except Exception:
        return None


def chain_label(status: dict) -> str:
    """Teks chip jaringan di topbar."""
    if not status["rpc"]:
        return "RPC mati"
    chain_id = status["chainId"]
    if status["expectedChainId"] and chain_id != status["expectedChainId"]:
        return f"Chain {chain_id} (harusnya {status['expectedChainId']})"
    return f"Localhost {chain_id}"
