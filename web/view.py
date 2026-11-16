"""Helper tampilan: label, format angka/alamat, filter, daftar navigasi.

Semua yang menerjemahkan data chain ke teks UI ada di sini supaya template
tetap tipis dan aturannya tidak tersebar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Urutan resmi enum Status di kontrak. Dipakai untuk stepper & filter.
STATUS_ORDER = ["CREATED", "EXAMINED", "DIAGNOSED", "TREATED", "COMPLETED"]

# Aksi di `getHistory()` → kalimat yang bisa dibaca.
HISTORY_LABELS = {
    "BATCH_CREATED": "Batch dibuat",
    "DOCTOR_ASSIGNED": "Dokter penanggung jawab diganti",
    "CONSENT_GRANTED": "Izin dokter diberikan",
    "CONSENT_REVOKED": "Izin dokter dicabut",
    "STATUS_UPDATED": "Status diperbarui",
    "TREATMENT_UPDATED": "Tindakan & obat diperbarui",
}

# Istilah teknis dibiarkan Inggris; yang diterjemahkan hanya label peran.
ROLE_LABELS = {
    "NONE": "Tanpa peran",
    "RECEPTIONIST": "Resepsionis",
    "DOCTOR": "Dokter",
    "ADMIN": "Admin",
    "PATIENT": "Pasien",
}

NAV = [
    {
        "title": "Ringkasan",
        "items": [
            {"label": "Dashboard", "href": "/", "icon": "dashboard"},
        ],
    },
    {
        "title": "Rekam Medis",
        "items": [
            {"label": "Daftar Batch", "href": "/rekam-medis", "icon": "folder"},
            {"label": "Buat Batch", "href": "/rekam-medis/baru", "icon": "note"},
        ],
    },
    {
        "title": "Akun",
        "items": [
            {"label": "Wallet & Transaksi", "href": "/wallet", "icon": "wallet"},
            {"label": "Hak Akses", "href": "/hak-akses", "icon": "shield"},
        ],
    },
]


def short_addr(address: str | None, head: int = 6, tail: int = 4) -> str:
    """`0x70997970…79C8` — alamat panjang dipotong di tengah."""
    if not address:
        return "—"
    if len(address) <= head + tail + 1:
        return address
    return f"{address[:head]}…{address[-tail:]}"


def fmt_number(value: Any) -> str:
    """Angka ribuan pakai pemisah titik (gaya Indonesia)."""
    if value is None:
        return "—"
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def fmt_eth(wei: Any, decimals: int = 4) -> str:
    """Saldo wei → ETH dengan 4 desimal."""
    if wei is None:
        return "—"
    try:
        eth = int(wei) / 10**18
    except (TypeError, ValueError):
        return "—"
    return f"{eth:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_datetime(timestamp: Any) -> str:
    """Unix timestamp → `16-11-2026 15:04` (waktu lokal mesin ini)."""
    if not timestamp:
        return "—"
    try:
        return datetime.fromtimestamp(int(timestamp)).strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return "—"


def status_label(status: Any) -> str:
    """Enum status (int) → nama yang dipakai kontrak."""
    if isinstance(status, int) and 0 <= status < len(STATUS_ORDER):
        return STATUS_ORDER[status]
    return str(status)


def next_status(status: Any) -> str | None:
    """Status berikutnya, atau None kalau sudah COMPLETED."""
    if isinstance(status, int) and 0 <= status < len(STATUS_ORDER) - 1:
        return STATUS_ORDER[status + 1]
    return None


def role_label(role: Any) -> str:
    """Enum peran (int/str) → label Indonesia."""
    names = ["NONE", "RECEPTIONIST", "DOCTOR", "ADMIN"]
    if isinstance(role, int) and 0 <= role < len(names):
        return ROLE_LABELS[names[role]]
    return ROLE_LABELS.get(str(role), "Tanpa peran")


def is_active(path: str, href: str) -> bool:
    """Tandai item navigasi yang sedang dibuka."""
    if href == "/":
        return path == "/"
    if path == href:
        return True
    # halaman detail /rekam-medis/{id} tetap menyalakan "Daftar Batch";
    # form /rekam-medis/baru punya item navigasi sendiri.
    return (
        href == "/rekam-medis"
        and path.startswith("/rekam-medis/")
        and path != "/rekam-medis/baru"
    )


# --------------------------------------------------------------------------
# Daftar batch: filter & ringkasan
# --------------------------------------------------------------------------


def status_index(status: Any) -> int:
    """Posisi status di `STATUS_ORDER` (0–4); -1 kalau tidak dikenal."""
    label = status_label(status)
    return STATUS_ORDER.index(label) if label in STATUS_ORDER else -1


def progress(status: Any) -> dict:
    """Untuk stepper mini: `1/5`, `2/5`, …"""
    index = status_index(status)
    return {
        "step": index + 1,
        "total": len(STATUS_ORDER),
        "finished": index == len(STATUS_ORDER) - 1,
    }


def filter_batches(
    batches: list[dict],
    *,
    q: str = "",
    status: str = "",
    doctor: str = "",
    wallet: str = "",
    mine: bool = False,
) -> list[dict]:
    """Terapkan filter daftar. Semua perbandingan case-insensitive."""
    needle = q.strip().lower()
    status = status.strip().upper()
    doctor = doctor.strip().lower()
    wallet = wallet.strip().lower()

    result = []
    for batch in batches:
        if status and status_label(batch.get("status")) != status:
            continue
        if doctor and str(batch.get("doctor", "")).lower() != doctor:
            continue
        if mine and wallet:
            if wallet not in (
                str(batch.get("patient", "")).lower(),
                str(batch.get("doctor", "")).lower(),
            ):
                continue
        if needle:
            haystack = (
                str(batch.get("patientId", "")).lower(),
                str(batch.get("patientName", "")).lower(),
                str(batch.get("tokenId", "")),
            )
            if not any(needle in value for value in haystack):
                continue
        result.append(batch)

    return result


def summary(batches: list[dict]) -> dict:
    """Angka ringkasan dashboard: total, pasien unik, selesai, proses."""
    counts = {name: 0 for name in STATUS_ORDER}
    patients = set()

    for batch in batches:
        label = status_label(batch.get("status"))
        if label in counts:
            counts[label] += 1
        patient = batch.get("patient")
        if patient:
            patients.add(str(patient).lower())

    total = len(batches)
    completed = counts["COMPLETED"]

    return {
        "total": total,
        "patients": len(patients),
        "completed": completed,
        "inProgress": total - completed,
        "counts": counts,
        "max": max(counts.values()) or 1,
    }


def history_label(action: str) -> str:
    """Nama aksi mentah kontrak → kalimat Indonesia."""
    return HISTORY_LABELS.get(action, action)


def register(env) -> None:
    """Daftarkan helper sebagai filter/global Jinja2."""
    env.filters["short_addr"] = short_addr
    env.filters["fmt_number"] = fmt_number
    env.filters["fmt_eth"] = fmt_eth
    env.filters["fmt_datetime"] = fmt_datetime
    env.filters["status_label"] = status_label
    env.filters["role_label"] = role_label
    env.filters["history_label"] = history_label
    env.globals["is_active"] = is_active
    env.globals["progress"] = progress
    env.globals["NAV"] = NAV
    env.globals["STATUS_ORDER"] = STATUS_ORDER
