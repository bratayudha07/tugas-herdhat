"""Helper tampilan: label, format angka/alamat, daftar navigasi.

Semua yang menerjemahkan data chain ke teks UI ada di sini supaya template
tetap tipis dan aturannya tidak tersebar.
"""

from __future__ import annotations

from typing import Any

# Urutan resmi enum Status di kontrak. Dipakai untuk stepper & filter.
STATUS_ORDER = ["CREATED", "EXAMINED", "DIAGNOSED", "TREATED", "COMPLETED"]

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
    # halaman detail /rekam-medis/{id} tetap menyalakan "Daftar Batch"
    return href == "/rekam-medis" and path.startswith("/rekam-medis/")


def register(env) -> None:
    """Daftarkan helper sebagai filter/global Jinja2."""
    env.filters["short_addr"] = short_addr
    env.filters["fmt_number"] = fmt_number
    env.filters["fmt_eth"] = fmt_eth
    env.filters["status_label"] = status_label
    env.filters["role_label"] = role_label
    env.globals["is_active"] = is_active
    env.globals["NAV"] = NAV
    env.globals["STATUS_ORDER"] = STATUS_ORDER
