"""Validasi input form — satu sumber aturan untuk server.

Template tidak mengulang aturan yang sama di JavaScript: halaman hanya
mengirim apa adanya, server memeriksa, lalu mengembalikan pesan per field
supaya UI bisa menampilkannya inline.

Aturan di sini lebih ketat dari kontrak (kontrak cuma menolak string kosong).
Itu disengaja: UI kelihatan serius, dan data demo tidak berisi sampah.
"""

from __future__ import annotations

import re

from web3 import Web3

# ID pasien: huruf/angka/strip, 3–32 karakter (mis. P-001).
PATIENT_ID = re.compile(r"^[A-Za-z0-9-]{3,32}$")

# Nama orang: huruf, spasi, titik, apostrof, strip. Angka ditolak karena
# hampir selalu tanda salah isi (mis. menempelkan nomor rekam medis).
PERSON_NAME = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,63}$")

# Skema yang masuk akal untuk metadata NFT di demo ini.
METADATA_PREFIXES = ("ipfs://", "https://", "data:application/json")

COMPLAINT_MIN = 5
COMPLAINT_MAX = 280

# Tindakan & obat juga pendek — ini catatan ringkas, bukan surat dokter.
TEXT_MAX = 280


def _text(value) -> str:
    """Nilai form → string rapi (None jadi kosong, spasi dipangkas)."""
    return str(value if value is not None else "").strip()


def token_id_arg(value) -> int | None:
    """Token ID dari payload JSON → int positif, atau None kalau ngawur."""
    try:
        token_id = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return token_id if token_id > 0 else None


def bool_arg(value) -> bool | None:
    """Boolean ketat: `true`/`false` (JSON maupun string), bukan truthy asal."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def address_arg(value) -> str | None:
    """Alamat 0x… → checksum, atau None kalau tidak valid."""
    text = _text(value)
    if not text or not Web3.is_address(text):
        return None
    return Web3.to_checksum_address(text)


def validate_create_batch(raw: dict, doctors: list[str]) -> tuple[dict, dict[str, str]]:
    """Periksa payload `createBatch`.

    Mengembalikan `(fields, errors)`; `fields` sudah dibersihkan dan siap
    dipakai membangun calldata, `errors` berisi pesan per nama field.
    """
    fields = {
        "patientId": _text(raw.get("patientId")),
        "patientName": _text(raw.get("patientName")),
        "complaint": _text(raw.get("complaint")),
        "patient": _text(raw.get("patient")),
        "doctor": _text(raw.get("doctor")),
        "metadata": _text(raw.get("metadata")),
    }
    errors: dict[str, str] = {}

    if not PATIENT_ID.match(fields["patientId"]):
        errors["patientId"] = (
            "ID pasien wajib diisi (3–32 karakter, huruf/angka/strip)."
        )

    name = fields["patientName"]
    if not name:
        errors["patientName"] = "Nama pasien wajib diisi."
    elif not PERSON_NAME.match(name):
        errors["patientName"] = (
            "Nama pasien 2–64 karakter, hanya huruf, spasi, titik, atau strip."
        )

    complaint = fields["complaint"]
    if not complaint:
        errors["complaint"] = "Keluhan wajib diisi."
    elif len(complaint) < COMPLAINT_MIN:
        errors["complaint"] = f"Keluhan minimal {COMPLAINT_MIN} karakter."
    elif len(complaint) > COMPLAINT_MAX:
        errors["complaint"] = (
            f"Keluhan maksimal {COMPLAINT_MAX} karakter (sekarang {len(complaint)})."
        )

    # Dokter harus salah satu hasil getDoctors() — bukan alamat bebas.
    registry = {address.lower(): address for address in doctors}
    if not fields["doctor"]:
        errors["doctor"] = "Pilih dokter penanggung jawab."
    elif fields["doctor"].lower() not in registry:
        errors["doctor"] = "Alamat dokter tidak terdaftar di kontrak."
    else:
        fields["doctor"] = registry[fields["doctor"].lower()]

    if not fields["patient"]:
        errors["patient"] = "Alamat wallet pasien wajib diisi."
    elif not Web3.is_address(fields["patient"]):
        errors["patient"] = "Alamat wallet tidak valid (0x + 40 digit hex)."
    else:
        fields["patient"] = Web3.to_checksum_address(fields["patient"])

    if fields["metadata"] and not fields["metadata"].startswith(METADATA_PREFIXES):
        errors["metadata"] = "Metadata harus diawali ipfs:// atau https://."

    return fields, errors


def error_summary(errors: dict[str, str]) -> str:
    """Kalimat ringkasan di atas form."""
    if len(errors) == 1:
        return "Ada 1 masalah pada form. Perbaiki dulu sebelum mengirim."
    return f"Ada {len(errors)} masalah pada form. Perbaiki dulu sebelum mengirim."


def validate_treatment(raw: dict) -> tuple[dict, dict[str, str]]:
    """Periksa payload `updateTreatment`.

    Kontrak hanya menolak kalau **dua-duanya** kosong, jadi aturan yang sama
    dipakai di sini. Pesan "minimal salah satu" ditempel ke field
    `treatment`; UI menampilkannya sekali di bawah pasangan input.
    """
    fields = {
        "treatment": _text(raw.get("treatment")),
        "medicine": _text(raw.get("medicine")),
    }
    errors: dict[str, str] = {}

    if not fields["treatment"] and not fields["medicine"]:
        errors["treatment"] = "Isi tindakan atau obat — minimal salah satu."

    for key, label in (("treatment", "Tindakan"), ("medicine", "Obat")):
        value = fields[key]
        if len(value) > TEXT_MAX:
            errors[key] = (
                f"{label} maksimal {TEXT_MAX} karakter (sekarang {len(value)})."
            )

    return fields, errors
