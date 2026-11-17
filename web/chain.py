"""Penghubung Web3.py ke Hardhat node.

Prinsip: server hanya membaca chain. Semua transaksi ditandatangani wallet
di browser (MetaMask), jadi tidak ada private key di proses Python.

Pembacaan di-cache sebentar (`config.CACHE_TTL`) supaya refresh halaman tidak
menembak RPC berulang kali — penting untuk laptop low-spec.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import requests
from web3 import Web3
from web3.providers.rpc.utils import ExceptionRetryConfiguration

from . import config

_cache: dict[str, tuple[float, Any]] = {}

_w3: Web3 | None = None


def get_web3() -> Web3:
    """Provider HTTP tunggal (dibuat sekali, dipakai ulang).

    `ExceptionRetryConfiguration` mengulang request yang gagal secara
    transport (timeout, 429, 5xx). Endpoint publik tanpa API key dipakai
    bersama banyak orang, jadi sesekali menolak sebentar — mengulang sekali
    dua kali jauh lebih baik daripada halaman ikut menampilkan error.
    Kalau kegagalannya memang berulang, error-nya tetap dilempar apa adanya.
    """
    global _w3
    if _w3 is None:
        _w3 = Web3(
            Web3.HTTPProvider(
                config.RPC_URL,
                request_kwargs={"timeout": config.RPC_TIMEOUT},
                exception_retry_configuration=ExceptionRetryConfiguration(
                    errors=(ConnectionError, requests.HTTPError, requests.Timeout),
                    retries=2,
                    backoff_factor=0.4,
                ),
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
        address = info["address"]
        checksum = Web3.to_checksum_address(address) if address else None

        # Satu request batch: chain id, blok, dan kode kontrak. Dipisah, tiga
        # panggilan ini makan ~1,3 detik di RPC publik.
        with w3.batch_requests() as batch:
            batch.add(w3.eth.chain_id)
            batch.add(w3.eth.block_number)
            if checksum is not None:
                batch.add(w3.eth.get_code(checksum))
            hasil = batch.execute()

        info["rpc"] = True
        info["chainId"] = int(hasil[0])
        info["block"] = int(hasil[1])

        if checksum is None:
            info["error"] = "deployment.json belum punya alamat kontrak"
            return info

        info["contract"] = len(hasil[2]) > 2
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

    w3 = get_web3()
    with w3.batch_requests() as batch:
        batch.add(contract.functions.name())
        batch.add(contract.functions.symbol())
        batch.add(contract.functions.totalSupply())
        batch.add(contract.functions.getDoctors())
        nama, simbol, total, dokter = batch.execute()

    return {
        "name": nama,
        "symbol": simbol,
        "totalSupply": total,
        "doctorCount": len(dokter),
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
    di-restart dan tidak perlu indexer. `getBatch()` untuk semua token
    dikirim sebagai satu batch request — satu per satu terlalu lambat di
    RPC publik (~0,5 detik per panggilan).
    """
    contract = get_contract()
    if contract is None:
        raise RuntimeError("Kontrak belum siap")

    total = int(contract.functions.totalSupply().call())
    if total == 0:
        return []

    w3 = get_web3()
    with w3.batch_requests() as batch:
        for token_id in range(1, total + 1):
            batch.add(contract.functions.getBatch(token_id))
        hasil = batch.execute()

    return [batch_dict(raw) for raw in hasil]


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
        w3 = get_web3()
        with w3.batch_requests() as batch:
            batch.add(contract.functions.getBatch(token_id))
            batch.add(contract.functions.getHistory(token_id))
            raw, history = batch.execute()

        batch = batch_dict(raw)
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


def consent_map(pairs: list[tuple[int, str]]) -> dict[int, bool]:
    """Izin untuk banyak batch sekaligus, satu request batch.

    Dipakai halaman Hak Akses yang menampilkan izin per baris. Tanpa batch,
    membaca izin satu per satu berarti satu round trip per batch — di RPC
    publik itu terasa detikan.
    """
    contract = get_contract()
    if contract is None or not pairs:
        return {}

    cleaned = []
    for token_id, doctor in pairs:
        if not doctor:
            continue
        try:
            cleaned.append((int(token_id), Web3.to_checksum_address(doctor)))
        except ValueError:
            continue

    if not cleaned:
        return {}

    key = "consents:" + ",".join(f"{token}:{doctor.lower()}" for token, doctor in cleaned)

    def read() -> dict[int, bool]:
        w3 = get_web3()
        with w3.batch_requests() as batch:
            for token_id, doctor in cleaned:
                batch.add(contract.functions.consent(token_id, doctor))
            hasil = batch.execute()

        return {
            token_id: bool(value)
            for (token_id, _doctor), value in zip(cleaned, hasil)
        }

    try:
        return _cached(key, read) or {}
    except Exception:
        return {}


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


def balances(addresses: list[str]) -> dict[str, float]:
    """Saldo banyak alamat dalam **satu** request RPC (JSON-RPC batch).

    Kartu akun demo menampilkan 8 saldo sekaligus. Dibaca satu per satu,
    endpoint publik tanpa API key bakal men-throttle dan halaman terasa
    menggantung belasan detik; satu request batch menyelesaikannya sekali
    jalan. Hasilnya dipetakan per alamat checksum.
    """
    checksums = []
    for address in addresses:
        if address and Web3.is_address(address):
            checksums.append(Web3.to_checksum_address(address))

    if not checksums:
        return {}

    key = "balances:" + ",".join(item.lower() for item in checksums)

    def read() -> dict[str, float]:
        w3 = get_web3()
        with w3.batch_requests() as batch:
            for address in checksums:
                batch.add(w3.eth.get_balance(address))
            values = batch.execute()

        return {
            address: float(Web3.from_wei(value, "ether"))
            for address, value in zip(checksums, values)
        }

    # Gagal baca bukan alasan menggagalkan halaman: saldo ditampilkan "—".
    try:
        return _cached(key, read) or {}
    except Exception:
        return {}


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


def roles(addresses: list[str]) -> dict[str, dict]:
    """Peran banyak alamat lewat satu request batch `eth_call`.

    Sama alasannya dengan `balances()`: membaca `getRole()` satu per satu ke
    endpoint publik tanpa API key makan waktu sekitar 1 detik per alamat,
    jadi 8 akun demo = 8 detik hanya untuk peran. Satu batch menyelesaikannya
    dalam sekali perjalanan. Alamat bermasalah tidak masuk ke hasil.
    """
    contract = get_contract()
    if contract is None:
        return {}

    checksums = []
    for address in addresses:
        if not address:
            continue
        try:
            checksums.append(Web3.to_checksum_address(address))
        except ValueError:
            continue

    if not checksums:
        return {}

    key = "roles:" + ",".join(item.lower() for item in checksums)

    def read() -> dict[str, dict]:
        w3 = get_web3()
        payloads = [
            contract.encode_abi("getRole", args=[address]) for address in checksums
        ]

        with w3.batch_requests() as batch:
            for data in payloads:
                batch.add(w3.eth.call({"to": contract.address, "data": data}))
            results = batch.execute()

        out = {}
        for address, raw in zip(checksums, results):
            if isinstance(raw, (bytes, bytearray)):
                value = int.from_bytes(raw, "big")
            else:
                value = int(raw, 16)

            out[address] = {
                "address": address,
                "role": ROLE_NAMES[value] if 0 <= value < len(ROLE_NAMES) else "NONE",
                "roleIndex": value,
            }

        return out

    try:
        return _cached(key, read) or {}
    except Exception:
        return {}


def chain_label(status: dict) -> str:
    """Teks chip jaringan di topbar."""
    if not status["rpc"]:
        return "RPC mati"
    chain_id = status["chainId"]
    if status["expectedChainId"] and chain_id != status["expectedChainId"]:
        return f"Chain {chain_id} (harusnya {status['expectedChainId']})"
    return f"{config.network_label()} {chain_id}"
