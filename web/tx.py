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

from . import chain, config, validate

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

    # Dry-run: kalau ini revert, transaksi akan revert juga — jadi jangan
    # sampai user menandatangani transaksi yang pasti gagal.
    try:
        predicted = contract.functions.createBatch(*args).call({"from": sender})
    except ContractLogicError as exc:
        raise TxError(revert_reason(exc)) from exc
    except ValueError as exc:
        raise TxError(revert_reason(exc)) from exc

    return {
        "id": uuid4().hex,
        "action": "createBatch",
        "from": sender,
        "to": config.contract_address(),
        "data": contract.encode_abi("createBatch", args=args),
        "chainId": chain.health()["chainId"],
        "label": f"Buat batch {fields['patientName']}",
        "predictedTokenId": int(predicted),
        "metadata": metadata,
        "summary": {
            "patientId": fields["patientId"],
            "patientName": fields["patientName"],
            "complaint": fields["complaint"],
            "doctor": fields["doctor"],
            "patient": fields["patient"],
        },
    }


BUILDERS = {
    "createBatch": build_create_batch,
}


def build(payload: dict) -> dict:
    """Dispatch `POST /api/tx/build` berdasarkan `action`."""
    action = validate._text(payload.get("action"))
    builder = BUILDERS.get(action)
    if builder is None:
        raise TxError(f"Aksi transaksi tidak dikenal: {action or '(kosong)'}.")
    return builder(payload)


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
