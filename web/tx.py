"""Menyiapkan transaksi untuk ditandatangani MetaMask, dan membaca hasilnya.

Batas tanggung jawab: **tidak ada private key di sini**. Server hanya
memvalidasi input, menjalankan dry-run `.call({from})` supaya transaksi yang
pasti ditolak tidak perlu ditandatangani, lalu mengirim balik `to` + `data`.
Tanda tangan terjadi di browser.
"""

from __future__ import annotations

import base64
import json
import re
from uuid import uuid4

from web3 import Web3
from web3.exceptions import ContractLogicError, TransactionNotFound
from web3.logs import DISCARD

from . import chain, config, validate, view

# ABI error string standar Solidity: 0x08c379a0 + offset + panjang + isi.
_REASON_SELECTOR = "0x08c379a0"
_REASON_TEXT = re.compile(r"reverted with reason string '([^']+)'")
_TX_HASH = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")


class TxError(Exception):
    """Kegagalan yang aman ditampilkan ke pengguna (bukan stack trace)."""

    def __init__(self, message: str, *, fields: dict | None = None, status: int = 400):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}
        self.status = status


# --------------------------------------------------------------------------
# Helper
# --------------------------------------------------------------------------


def revert_reason(exc: Exception) -> str:
    """Ambil alasan revert asli kontrak (bahasa Indonesia), apa adanya.

    Hardhat membungkus pesan jadi `... reverted with reason string 'X'`, dan
    kadang hanya menyisakan payload ABI di `args`. Dua-duanya dicoba supaya
    pesan seperti "Pasien belum memberi izin" tidak hilang jadi pesan generik.
    """
    if exc.args and isinstance(exc.args[-1], dict):
        data = exc.args[-1].get("data")
        if isinstance(data, str) and data.startswith(_REASON_SELECTOR):
            try:
                decoded = chain.get_web3().codec.decode(
                    ["string"], bytes.fromhex(data[len(_REASON_SELECTOR) :])
                )
                if decoded and isinstance(decoded[0], str):
                    return decoded[0]
            except Exception:  # payload rusak — lanjut ke cara berikutnya
                pass

    match = _REASON_TEXT.search(str(exc))
    if match:
        return match.group(1)

    return "Kontrak menolak transaksi ini."


def _require_rpc() -> None:
    if not chain.health()["rpc"]:
        raise TxError("Hardhat RPC tidak dapat diakses.", status=503)


def _require_contract():
    contract = chain.get_contract()
    if contract is None:
        raise TxError("Kontrak belum siap dibaca. Cek RPC dan deployment.json.", status=503)
    return contract


def _sender(payload: dict) -> str:
    sender = validate._text(payload.get("from"))
    if not sender or not Web3.is_address(sender):
        raise TxError("Alamat wallet pengirim tidak valid.", status=400)
    return Web3.to_checksum_address(sender)


def auto_metadata() -> str:
    """Metadata NFT default: `data:application/json;base64,…`.

    Sengaja tanpa nama/ID pasien — metadata ini ikut tersimpan di chain,
    jadi jangan menambah PII baru di luar yang sudah ada di kontrak.
    """
    payload = {
        "name": "EHR Batch",
        "description": (
            "Rekam medis pasien on-chain (EHR Traceability). Data klinis "
            "disimpan di kontrak, bukan di metadata ini."
        ),
        "attributes": [{"trait_type": "status", "value": "CREATED"}],
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "data:application/json;base64," + base64.b64encode(raw).decode("ascii")


# --------------------------------------------------------------------------
# Kerangka umum: dry-run → calldata
# --------------------------------------------------------------------------


def _prepare(contract, fn_name: str, args: list, sender: str):
    """Jalankan fungsi sebagai `sender` tanpa mengirim transaksi.

    Kalau ini revert, transaksi sungguhan juga akan revert — jadi user tidak
    perlu menandatangani transaksi yang pasti gagal. Nilai baliknya dipakai
    untuk data yang hanya diketahui setelah eksekusi (mis. token ID baru).
    """
    try:
        return getattr(contract.functions, fn_name)(*args).call({"from": sender})
    except ContractLogicError as exc:
        raise TxError(revert_reason(exc)) from exc
    except ValueError as exc:
        raise TxError(revert_reason(exc)) from exc


def _rows(*pairs) -> list[dict]:
    """Ringkasan transaksi: list `{label, value}`, urutan dipertahankan.

    Nilai kosong ditulis "—" supaya dialog tidak menampilkan baris menggantung.
    """
    return [
        {"label": label, "value": "—" if value in (None, "") else str(value)}
        for label, value in pairs
    ]


def _signed(
    contract,
    action: str,
    fn_name: str,
    args: list,
    sender: str,
    *,
    label: str,
    summary: list[dict],
    predicted_token_id: int | None = None,
    extra: dict | None = None,
) -> dict:
    """Payload yang dikirim ke wallet: `to` + `data`, tanpa private key."""
    payload = {
        "id": uuid4().hex,
        "action": action,
        "from": sender,
        "to": config.contract_address(),
        "data": contract.encode_abi(fn_name, args=args),
        "chainId": chain.health()["chainId"],
        "label": label,
        "summary": summary,
        "predictedTokenId": predicted_token_id,
    }
    if extra:
        payload.update(extra)
    return payload


def _token_arg(payload: dict) -> int:
    token_id = validate.token_id_arg((payload.get("args") or {}).get("tokenId"))
    if token_id is None:
        raise TxError("Token ID tidak valid.")
    return token_id


def _batch_or_error(contract, token_id: int) -> dict:
    """Baca batch; alasan revert kontrak diteruskan apa adanya."""
    try:
        return chain.batch_dict(contract.functions.getBatch(token_id).call())
    except (ContractLogicError, ValueError) as exc:
        raise TxError(revert_reason(exc)) from exc


def _current_status(batch: dict) -> str:
    return view.STATUS_ORDER[batch["status"]]


# --------------------------------------------------------------------------
# createBatch
# --------------------------------------------------------------------------


def build_create_batch(payload: dict) -> dict:
    """Validasi → dry-run → calldata siap tanda tangan."""
    _require_rpc()
    sender = _sender(payload)
    contract = _require_contract()

    fields, errors = validate.validate_create_batch(
        payload.get("args") or {}, chain.doctors()
    )
    if errors:
        raise TxError(validate.error_summary(errors), fields=errors)

    metadata = fields["metadata"] or auto_metadata()
    args = [
        fields["patientId"],
        fields["patientName"],
        fields["complaint"],
        fields["patient"],
        fields["doctor"],
        metadata,
    ]

    predicted = _prepare(contract, "createBatch", args, sender)

    return _signed(
        contract,
        "createBatch",
        "createBatch",
        args,
        sender,
        label=f"Buat batch {fields['patientName']}",
        summary=_rows(
            ("Pasien", fields["patientName"]),
            ("ID pasien", fields["patientId"]),
            ("Keluhan", fields["complaint"]),
            ("Dokter", fields["doctor"]),
            ("Wallet pasien", fields["patient"]),
            ("Token ID (simulasi)", f"#{int(predicted)}"),
        ),
        predicted_token_id=int(predicted),
        extra={"metadata": metadata},
    )


# --------------------------------------------------------------------------
# updateStatus / updateTreatment / setConsent / assignDoctor
# --------------------------------------------------------------------------


def build_update_status(payload: dict) -> dict:
    """Majukan status tepat satu tahap — kontrak menolak lompatan."""
    _require_rpc()
    sender = _sender(payload)
    contract = _require_contract()
    token_id = _token_arg(payload)

    batch = _batch_or_error(contract, token_id)
    target_index = batch["status"] + 1
    if target_index >= len(view.STATUS_ORDER):
        raise TxError("Rekam medis sudah selesai — status tidak bisa dimajukan lagi.")

    target = view.STATUS_ORDER[target_index]
    args = [token_id, target_index]
    _prepare(contract, "updateStatus", args, sender)

    return _signed(
        contract,
        "updateStatus",
        "updateStatus",
        args,
        sender,
        label=f"Majukan status #{token_id} ke {target}",
        summary=_rows(
            ("Batch", f"#{token_id} · {batch['patientName']}"),
            ("Status sekarang", _current_status(batch)),
            ("Status baru", target),
        ),
    )


def build_update_treatment(payload: dict) -> dict:
    """Simpan tindakan & obat. Minimal salah satu harus terisi."""
    _require_rpc()
    sender = _sender(payload)
    contract = _require_contract()
    token_id = _token_arg(payload)

    fields, errors = validate.validate_treatment(payload.get("args") or {})
    if errors:
        raise TxError(validate.error_summary(errors), fields=errors)

    batch = _batch_or_error(contract, token_id)
    args = [token_id, fields["treatment"], fields["medicine"]]
    _prepare(contract, "updateTreatment", args, sender)

    return _signed(
        contract,
        "updateTreatment",
        "updateTreatment",
        args,
        sender,
        label=f"Simpan tindakan #{token_id}",
        summary=_rows(
            ("Batch", f"#{token_id} · {batch['patientName']}"),
            ("Tindakan", fields["treatment"]),
            ("Obat", fields["medicine"]),
        ),
    )


def build_set_consent(payload: dict) -> dict:
    """Pasien memberi / mencabut izin untuk dokter penanggung jawab."""
    _require_rpc()
    sender = _sender(payload)
    contract = _require_contract()
    token_id = _token_arg(payload)

    granted = validate.bool_arg((payload.get("args") or {}).get("granted"))
    if granted is None:
        raise TxError("Status izin harus true atau false.")

    batch = _batch_or_error(contract, token_id)
    args = [token_id, granted]
    _prepare(contract, "setConsent", args, sender)

    verb = "Izinkan" if granted else "Cabut izin"
    return _signed(
        contract,
        "setConsent",
        "setConsent",
        args,
        sender,
        label=f"{verb} dokter batch #{token_id}",
        summary=_rows(
            ("Batch", f"#{token_id} · {batch['patientName']}"),
            ("Dokter", batch["doctor"]),
            ("Izin setelah ini", "Aktif — dokter boleh menulis" if granted else "Nonaktif — dokter tidak boleh menulis"),
        ),
    )


def build_assign_doctor(payload: dict) -> dict:
    """Resepsionis mengganti dokter penanggung jawab.

    Kontrak mencabut izin dokter lama. Peringatan itu ikut di ringkasan
    supaya user tahu konsekuensinya sebelum tanda tangan.
    """
    _require_rpc()
    sender = _sender(payload)
    contract = _require_contract()
    token_id = _token_arg(payload)

    requested = validate.address_arg((payload.get("args") or {}).get("doctor"))
    if requested is None:
        raise TxError("Alamat dokter tidak valid.")

    registry = {address.lower(): address for address in chain.doctors()}
    doctor = registry.get(requested.lower())
    if doctor is None:
        raise TxError(
            "Alamat dokter tidak terdaftar di kontrak.",
            fields={"doctor": "Pilih dokter dari daftar getDoctors()."},
        )

    batch = _batch_or_error(contract, token_id)
    if batch["doctor"] and batch["doctor"].lower() == doctor.lower():
        raise TxError("Dokter itu sudah menjadi penanggung jawab batch ini.")

    args = [token_id, doctor]
    _prepare(contract, "assignDoctor", args, sender)

    return _signed(
        contract,
        "assignDoctor",
        "assignDoctor",
        args,
        sender,
        label=f"Ganti dokter penanggung jawab #{token_id}",
        summary=_rows(
            ("Batch", f"#{token_id} · {batch['patientName']}"),
            ("Dokter sekarang", batch["doctor"]),
            ("Dokter baru", doctor),
            ("Izin dokter lama", "Dicabut otomatis oleh kontrak"),
        ),
    )


BUILDERS = {
    "createBatch": build_create_batch,
    "updateStatus": build_update_status,
    "updateTreatment": build_update_treatment,
    "setConsent": build_set_consent,
    "assignDoctor": build_assign_doctor,
}


def build(payload: dict) -> dict:
    """Dispatch `POST /api/tx/build` berdasarkan `action`."""
    action = validate._text(payload.get("action"))
    builder = BUILDERS.get(action)
    if builder is None:
        raise TxError(f"Aksi transaksi tidak dikenal: {action or '(kosong)'}.")
    return builder(payload)


# --------------------------------------------------------------------------
# Konteks otorisasi satu batch
# --------------------------------------------------------------------------


def batch_context(token_id: int, address: str) -> dict | None:
    """Apa yang boleh dilakukan `address` pada batch ini.

    Dibaca ulang tiap kali wallet berganti akun, jadi tombol yang tampil
    selalu sesuai state chain — bukan tebakan dari halaman yang sudah basi.

    `None` = batch tidak ada (404). TxError 503 = RPC/kontrak belum siap.
    """
    _require_rpc()
    contract = _require_contract()

    info = chain.role_of(address)
    if info is None:
        raise TxError("Alamat wallet tidak valid.")

    try:
        batch = chain.batch_dict(contract.functions.getBatch(token_id).call())
    except (ContractLogicError, ValueError):
        return None

    role = info["role"]
    is_owner = batch["patient"].lower() == info["address"].lower()

    # Peran NONE + pemilik NFT = pasien. Aturan ini sama dengan topbar,
    # supaya label peran tidak berbeda antar halaman.
    if role == "NONE" and is_owner:
        role = "PATIENT"

    is_assigned = bool(batch["doctor"]) and (
        batch["doctor"].lower() == info["address"].lower()
    )
    consent = None
    if batch["doctor"]:
        consent = chain.consent_of(token_id, batch["doctor"])

    completed = batch["status"] >= len(view.STATUS_ORDER) - 1
    doctor_may_write = role == "DOCTOR" and is_assigned and consent is True

    return {
        "tokenId": token_id,
        "status": _current_status(batch),
        "nextStatus": view.next_status(batch["status"]),
        "completed": completed,
        "doctor": batch["doctor"],
        "patient": batch["patient"],
        "role": role,
        "roleLabel": view.role_label(role),
        "isOwner": is_owner,
        "isAssignedDoctor": is_assigned,
        "consent": consent,
        "canAdvance": doctor_may_write and not completed,
        "canTreat": doctor_may_write and not completed,
        "canConsent": role == "PATIENT" and not completed and bool(batch["doctor"]),
        "canAssignDoctor": role == "RECEPTIONIST" and not completed,
    }


# --------------------------------------------------------------------------
# Status transaksi
# --------------------------------------------------------------------------


def _token_id_from_receipt(receipt) -> int | None:
    """Token ID baru dari event `BatchCreated` (kalau ada di receipt)."""
    contract = chain.get_contract()
    if contract is None:
        return None

    try:
        # DISCARD: log lain (mis. Transfer ERC-721) tidak perlu jadi warning.
        events = contract.events.BatchCreated().process_receipt(
            receipt, errors=DISCARD
        )
    except Exception:
        return None

    for event in events:
        token_id = event.get("args", {}).get("tokenId")
        if token_id is not None:
            return int(token_id)
    return None


def _failure_reason(receipt) -> str | None:
    """Best effort: ulang transaksi di state sebelum bloknya untuk ambil alasan.

    Receipt transaksi yang gagal tidak menyimpan alasan revert, jadi satu-
    satunya cara adalah replay `eth_call`. Kalau replay juga gagal karena hal
    lain, kembalikan None — UI akan pakai pesan umum.
    """
    try:
        chain.get_web3().eth.call(
            {
                "from": receipt["from"],
                "to": receipt["to"],
                "data": receipt["input"],
            },
            block_identifier=max(int(receipt.blockNumber) - 1, 0),
        )
    except ContractLogicError as exc:
        return revert_reason(exc)
    except Exception:
        return None
    return None


def tx_status(tx_hash: str) -> dict:
    """Status satu transaksi: pending / success / failed + detail receipt."""
    raw = validate._text(tx_hash)
    if not _TX_HASH.match(raw):
        raise TxError("Hash transaksi tidak valid.", status=400)
    # HexBytes.hex() di web3 8 tidak selalu membawa awalan 0x; URL dari
    # MetaMask selalu membawanya. Dua-duanya diterima.
    tx_hash = raw if raw.startswith("0x") else f"0x{raw}"

    _require_rpc()

    try:
        receipt = chain.get_web3().eth.get_transaction_receipt(tx_hash)
    except TransactionNotFound:
        # Normal: transaksi sudah dikirim wallet tapi belum ditambang.
        return {"state": "pending", "hash": tx_hash}
    except Exception as exc:
        raise TxError(f"Gagal membaca transaksi: {exc}", status=502) from exc

    if receipt is None:
        return {"state": "pending", "hash": tx_hash}

    ok = int(receipt.status) == 1
    result = {
        "state": "success" if ok else "failed",
        "hash": tx_hash,
        "block": int(receipt.blockNumber),
        "gas": int(receipt.gasUsed),
        "from": receipt["from"],
        "to": receipt["to"],
        "tokenId": None,
        "reason": None,
    }

    if ok:
        result["tokenId"] = _token_id_from_receipt(receipt)
        # Data baru sudah masuk chain — buang cache baca supaya halaman
        # berikutnya tidak menampilkan daftar lama.
        chain.refresh()
    else:
        result["reason"] = _failure_reason(receipt)

    return result
