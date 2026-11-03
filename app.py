import json
import re
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components
from web3 import Web3
from web3.exceptions import ContractLogicError
from web3.logs import DISCARD

# =========================================================
# KONFIGURASI
# =========================================================

RPC_URL = "http://127.0.0.1:8545"

BASE_DIR = Path(__file__).resolve().parent
ARTIFACT_PATH = (
    BASE_DIR
    / "artifacts"
    / "contracts"
    / "EHRTraceability.sol"
    / "EHRTraceability.json"
)
DEPLOYMENT_PATH = BASE_DIR / "deployment.json"

# Urutan harus sama dengan enum Status di EHRTraceability.sol
STATUS_LABELS = [
    "CREATED (Dibuat)",
    "EXAMINED (Diperiksa)",
    "DIAGNOSED (Didiagnosis)",
    "TREATED (Ditangani)",
    "COMPLETED (Selesai)",
]

ACTION_LABELS = {
    "BATCH_CREATED": "Batch dibuat",
    "STATUS_UPDATED": "Status diperbarui",
    "TREATMENT_UPDATED": "Tindakan & obat diisi",
}

st.set_page_config(
    page_title="EHR Traceability",
    page_icon="🏥",
    layout="centered",
)

st.title("🏥 EHR Traceability")
st.caption(
    "Rekam medis pasien sebagai NFT (ERC-721) - "
    "Hardhat + MetaMask + Streamlit + Web3.py"
)

# =========================================================
# KOMPONEN JAVASCRIPT UNTUK METAMASK
# =========================================================

WALLET_HTML = """
<div>
  <button id="connect-wallet" type="button">
    Connect Wallet
  </button>
  <p id="wallet-status">Wallet belum terhubung.</p>
</div>
"""

WALLET_CSS = """
button {
    padding: 0.7rem 1rem;
    border: none;
    border-radius: 8px;
    background: var(--st-primary-color);
    color: white;
    font-weight: 600;
    cursor: pointer;
}

button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

p {
    color: var(--st-text-color);
    overflow-wrap: anywhere;
}
"""

WALLET_JS = """
export default function(component) {
    const { parentElement, setStateValue } = component;

    const button = parentElement.querySelector("#connect-wallet");
    const status = parentElement.querySelector("#wallet-status");

    let mounted = true;

    async function readWallet() {
        if (!window.ethereum) {
            return;
        }

        const accounts = await window.ethereum.request({
            method: "eth_accounts"
        });

        const chainId = await window.ethereum.request({
            method: "eth_chainId"
        });

        if (!mounted) return;

        if (accounts && accounts.length > 0) {
            setStateValue("wallet", {
                address: accounts[0],
                chainId: chainId,
                connected: true
            });
            status.textContent = "Wallet terhubung: " + accounts[0];
        } else {
            setStateValue("wallet", {
                address: "",
                chainId: chainId,
                connected: false
            });
            status.textContent = "Wallet belum terhubung.";
        }
    }

    async function connectWallet() {
        if (!window.ethereum) {
            status.textContent =
                "MetaMask tidak ditemukan. Pasang ekstensi MetaMask.";
            return;
        }

        try {
            status.textContent =
                "Menunggu persetujuan akses akun...";

            await window.ethereum.request({
                method: "eth_requestAccounts"
            });

            await readWallet();
        } catch (error) {
            status.textContent =
                "Koneksi gagal: " +
                (error.message || "Kesalahan tidak diketahui");
        }
    }

    function onAccountsChanged(accounts) {
        if (!mounted) return;

        window.ethereum.request({ method: "eth_chainId" })
            .then((chainId) => {
                if (!mounted) return;

                if (accounts && accounts.length > 0) {
                    setStateValue("wallet", {
                        address: accounts[0],
                        chainId: chainId,
                        connected: true
                    });
                    status.textContent =
                        "Wallet terhubung: " + accounts[0];
                } else {
                    setStateValue("wallet", {
                        address: "",
                        chainId: chainId,
                        connected: false
                    });
                    status.textContent = "Akun tidak terhubung.";
                }
            })
            .catch(() => {});
    }

    function onChainChanged(chainId) {
        if (!mounted) return;

        window.ethereum.request({ method: "eth_accounts" })
            .then((accounts) => {
                if (!mounted) return;

                setStateValue("wallet", {
                    address: accounts && accounts.length > 0
                        ? accounts[0]
                        : "",
                    chainId: chainId,
                    connected: Boolean(accounts && accounts.length > 0)
                });
            })
            .catch(() => {});
    }

    button.addEventListener("click", connectWallet);

    if (window.ethereum) {
        window.ethereum.on("accountsChanged", onAccountsChanged);
        window.ethereum.on("chainChanged", onChainChanged);

        // Baca koneksi yang sudah pernah diberikan izin.
        readWallet().catch(() => {});
    }

    return () => {
        mounted = false;
        button.removeEventListener("click", connectWallet);

        if (window.ethereum && window.ethereum.removeListener) {
            window.ethereum.removeListener(
                "accountsChanged", onAccountsChanged
            );
            window.ethereum.removeListener(
                "chainChanged", onChainChanged
            );
        }
    };
}
"""

wallet_component = components.component(
    name="ehr_metamask_wallet",
    html=WALLET_HTML,
    css=WALLET_CSS,
    js=WALLET_JS,
)

# Komponen kedua: mengirim transaksi yang sudah disiapkan Python
# (to + data hasil encode ABI) ke MetaMask untuk ditandatangani.
# Private key tidak pernah menyentuh Python.

TX_HTML = """
<div>
  <button id="send-tx" type="button">Konfirmasi di MetaMask</button>
  <p id="tx-status">Klik tombol untuk membuka MetaMask.</p>
</div>
"""

TX_JS = """
export default function(component) {
    const { parentElement, data, setTriggerValue } = component;

    const button = parentElement.querySelector("#send-tx");
    const status = parentElement.querySelector("#tx-status");

    async function sendTransaction() {
        if (!window.ethereum) {
            status.textContent =
                "MetaMask tidak ditemukan. Pasang ekstensi MetaMask.";
            return;
        }

        button.disabled = true;
        status.textContent = "Menunggu konfirmasi di MetaMask...";

        try {
            const hash = await window.ethereum.request({
                method: "eth_sendTransaction",
                params: [{
                    from: data.from,
                    to: data.to,
                    data: data.data
                }]
            });

            status.textContent = "Transaksi terkirim: " + hash;
            setTriggerValue("result", { id: data.id, hash: hash });
        } catch (error) {
            button.disabled = false;
            status.textContent =
                "Transaksi dibatalkan/gagal: " +
                (error.message || "Kesalahan tidak diketahui");
        }
    }

    button.onclick = sendTransaction;

    return () => {
        button.onclick = null;
    };
}
"""

tx_component = components.component(
    name="ehr_metamask_tx",
    html=TX_HTML,
    css=WALLET_CSS,
    js=TX_JS,
)

# =========================================================
# HELPER
# =========================================================


def format_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%d-%m-%Y %H:%M:%S")


def status_label(status):
    if 0 <= status < len(STATUS_LABELS):
        return STATUS_LABELS[status]
    return f"Tidak dikenal ({status})"


def short_error(error):
    """Ambil alasan revert dari pesan error Hardhat/Web3.py."""
    message = getattr(error, "message", None) or str(error)
    for pattern in (
        r"reverted with reason string '([^']*)'",
        r"execution reverted: ?([^'\"]*)",
    ):
        match = re.search(pattern, message)
        if match:
            return match.group(1).strip()
    return message


def load_abi():
    if not ARTIFACT_PATH.exists():
        return None
    with ARTIFACT_PATH.open() as file:
        return json.load(file)["abi"]


def load_deployed_address():
    if not DEPLOYMENT_PATH.exists():
        return ""
    with DEPLOYMENT_PATH.open() as file:
        return json.load(file).get("address", "")


def get_batch(token_id):
    """Mengembalikan dict data batch, atau None jika tidak ditemukan."""
    try:
        batch = contract.functions.getBatch(token_id).call()
    except ContractLogicError:
        return None

    return {
        "tokenId": batch[0],
        "patientId": batch[1],
        "patientName": batch[2],
        "complaint": batch[3],
        "treatment": batch[4],
        "medicine": batch[5],
        "status": batch[6],
        "createdAt": batch[7],
        "owner": contract.functions.ownerOf(token_id).call(),
    }


def prepare_tx(tab, fn_name, args, label):
    """Simulasi transaksi lalu simpan sebagai transaksi tertunda."""
    try:
        getattr(contract.functions, fn_name)(*args).call(
            {"from": wallet_address}
        )
    except ContractLogicError as error:
        st.error(f"Transaksi akan ditolak kontrak: {short_error(error)}")
        return
    except Exception as error:
        st.error("Simulasi transaksi gagal.")
        st.caption(str(error))
        return

    st.session_state.pending_tx = {
        "id": str(time.time_ns()),
        "tab": tab,
        "fn": fn_name,
        "label": label,
        "from": wallet_address,
        "to": contract.address,
        "data": contract.encode_abi(fn_name, args=args),
    }


def handle_tx_hash(pending, tx_hash):
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    except Exception as error:
        st.session_state.last_tx[pending["tab"]] = {
            "label": pending["label"],
            "hash": tx_hash,
            "error": f"Gagal membaca receipt: {error}",
        }
        return

    result = {
        "label": pending["label"],
        "hash": tx_hash,
        "block": receipt["blockNumber"],
        "gas": receipt["gasUsed"],
        "success": receipt["status"] == 1,
    }

    if pending["fn"] == "createBatch" and result["success"]:
        events = contract.events.BatchCreated().process_receipt(
            receipt, errors=DISCARD
        )
        if events:
            result["tokenId"] = events[0]["args"]["tokenId"]

    st.session_state.last_tx[pending["tab"]] = result


def render_tx_area(tab):
    """Tampilkan hasil transaksi terakhir dan tombol MetaMask untuk tab ini."""
    last = st.session_state.last_tx.get(tab)
    if last:
        if last.get("error"):
            st.error(last["error"])
        elif last["success"]:
            message = f"Transaksi berhasil: {last['label']}"
            if "tokenId" in last:
                message += f" - Token ID baru: **{last['tokenId']}**"
            st.success(message)
            st.caption(
                f"Block {last['block']} - Gas terpakai {last['gas']:,}"
            )
        else:
            st.error(f"Transaksi gagal (reverted): {last['label']}")
        st.code(last["hash"])

    pending = st.session_state.pending_tx
    if not pending or pending["tab"] != tab:
        return

    st.info(f"Transaksi siap dikirim: **{pending['label']}**")

    result = tx_component(
        key=f"tx_{pending['id']}",
        data=pending,
        on_result_change=lambda: None,
    )

    if st.button("Batalkan transaksi", key=f"cancel_{pending['id']}"):
        st.session_state.pending_tx = None
        st.rerun()

    if result.result and result.result.get("id") == pending["id"]:
        handle_tx_hash(pending, result.result["hash"])
        st.session_state.pending_tx = None
        st.rerun()


st.session_state.setdefault("pending_tx", None)
st.session_state.setdefault("last_tx", {})

# =========================================================
# 1. KONEKSI KE HARDHAT RPC
# =========================================================

st.subheader("1. Status Blockchain Lokal")

w3 = Web3(
    Web3.HTTPProvider(
        RPC_URL,
        request_kwargs={"timeout": 5},
    )
)

rpc_connected = w3.is_connected()

if rpc_connected:
    st.success("Blockchain Hardhat berhasil dihubungkan.")

    col1, col2 = st.columns(2)

    col1.metric(
        "Chain ID RPC",
        w3.eth.chain_id,
    )

    col2.metric(
        "Block Terbaru",
        w3.eth.block_number,
    )

    st.code(RPC_URL)
else:
    st.error(
        "Hardhat RPC tidak dapat diakses. "
        "Jalankan 'npx hardhat node' pada terminal lain."
    )

# =========================================================
# 2. KONEKSI METAMASK
# =========================================================

st.divider()
st.subheader("2. Hubungkan MetaMask")

wallet_result = wallet_component(
    key="ehr_metamask",
    default={
        "wallet": {
            "address": "",
            "chainId": "",
            "connected": False,
        }
    },
    on_wallet_change=lambda: None,
)

wallet = wallet_result.wallet

# =========================================================
# 3. INFORMASI WALLET DAN SALDO
# =========================================================

st.divider()
st.subheader("3. Informasi Wallet")

wallet_address = ""
wallet_ready = False  # True jika wallet bisa dipakai untuk transaksi

if wallet and wallet.get("connected") and wallet.get("address"):
    wallet_address = Web3.to_checksum_address(wallet["address"])

    st.success("Wallet berhasil terhubung.")

    st.write("Alamat wallet:")
    st.code(wallet_address)

    try:
        wallet_chain_id = int(wallet["chainId"], 16)

        if not rpc_connected:
            st.metric("Chain ID MetaMask", wallet_chain_id)
            st.warning(
                "Wallet terhubung, tetapi RPC tidak tersedia. "
                "Saldo belum dapat dibaca."
            )

        elif wallet_chain_id != w3.eth.chain_id:
            st.metric("Chain ID MetaMask", wallet_chain_id)
            st.warning(
                "Jaringan MetaMask berbeda dengan jaringan RPC Python. "
                "Pilih jaringan Hardhat Local pada MetaMask."
            )

        else:
            wallet_ready = True

            balance_eth = w3.from_wei(
                w3.eth.get_balance(wallet_address),
                "ether",
            )

            col1, col2 = st.columns(2)
            col1.metric("Chain ID MetaMask", wallet_chain_id)
            col2.metric("Saldo ETH", f"{float(balance_eth):.6f} ETH")

            st.caption(
                "Jaringan wallet sesuai dengan RPC. "
                "Saldo dibaca oleh Web3.py dari Hardhat RPC."
            )

    except (ValueError, TypeError) as error:
        st.error("Data Chain ID dari MetaMask tidak valid.")
        st.caption(str(error))

else:
    st.info(
        "Klik Connect Wallet, kemudian setujui akses akun di MetaMask."
    )

# =========================================================
# 4. SMART CONTRACT
# =========================================================

st.divider()
st.subheader("4. Smart Contract EHRTraceability")

abi = load_abi()

if abi is None:
    st.error(
        "ABI kontrak tidak ditemukan. Jalankan 'npx hardhat compile' "
        "terlebih dahulu."
    )
    st.stop()

contract_address_input = st.text_input(
    "Alamat kontrak",
    value=load_deployed_address(),
    help=(
        "Terisi otomatis dari deployment.json yang dibuat oleh "
        "scripts/deploy.js."
    ),
)

if not rpc_connected:
    st.warning("Hubungkan Hardhat RPC untuk memakai smart contract.")
    st.stop()

if not Web3.is_address(contract_address_input):
    st.warning(
        "Alamat kontrak belum diisi atau tidak valid. Deploy kontrak dengan "
        "'npx hardhat run scripts/deploy.js --network localhost'."
    )
    st.stop()

contract_address = Web3.to_checksum_address(contract_address_input)

if w3.eth.get_code(contract_address) in (b"", b"\x00"):
    st.error(
        "Tidak ada kontrak pada alamat ini. Jika node Hardhat baru "
        "dijalankan ulang, deploy ulang kontraknya."
    )
    st.stop()

contract = w3.eth.contract(address=contract_address, abi=abi)

col1, col2 = st.columns(2)
col1.metric("Nama NFT", contract.functions.name().call())
col2.metric("Simbol", contract.functions.symbol().call())

# =========================================================
# 5. REKAM MEDIS
# =========================================================

st.divider()
st.subheader("5. Rekam Medis Pasien")

tab_list, tab_detail, tab_create, tab_status, tab_treatment = st.tabs(
    [
        "Daftar Batch",
        "Detail & Riwayat",
        "Buat Batch",
        "Update Status",
        "Tindakan & Obat",
    ]
)


def require_wallet():
    if wallet_ready:
        return True
    st.info(
        "Hubungkan MetaMask ke jaringan Hardhat Local untuk "
        "mengirim transaksi."
    )
    return False


# ---------------------------------------------------------
# DAFTAR BATCH (dibaca dari event BatchCreated)
# ---------------------------------------------------------

with tab_list:
    created_events = contract.events.BatchCreated().get_logs(from_block=0)

    only_mine = st.checkbox(
        "Hanya batch milik wallet saya",
        disabled=not wallet_address,
    )

    rows = []
    for event in created_events:
        batch = get_batch(event["args"]["tokenId"])
        if batch is None:
            continue
        if only_mine and batch["owner"] != wallet_address:
            continue
        rows.append(
            {
                "Token ID": batch["tokenId"],
                "ID Pasien": batch["patientId"],
                "Nama Pasien": batch["patientName"],
                "Status": status_label(batch["status"]),
                "Pemilik": batch["owner"],
                "Dibuat": format_time(batch["createdAt"]),
            }
        )

    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.info("Belum ada batch rekam medis.")

# ---------------------------------------------------------
# DETAIL & RIWAYAT (getBatch + getHistory)
# ---------------------------------------------------------

with tab_detail:
    detail_id = st.number_input(
        "Token ID", min_value=1, step=1, value=1, key="detail_id"
    )

    batch = get_batch(int(detail_id))

    if batch is None:
        st.warning("Batch tidak ditemukan.")
    else:
        col1, col2 = st.columns(2)
        col1.metric("Status", status_label(batch["status"]))
        col2.metric("Dibuat", format_time(batch["createdAt"]))

        st.markdown(
            f"""
| Data | Nilai |
|---|---|
| ID Pasien | {batch["patientId"]} |
| Nama Pasien | {batch["patientName"]} |
| Keluhan | {batch["complaint"]} |
| Tindakan | {batch["treatment"] or "-"} |
| Obat | {batch["medicine"] or "-"} |
"""
        )

        st.write("Pemilik NFT:")
        st.code(batch["owner"])

        token_uri = contract.functions.tokenURI(int(detail_id)).call()
        if token_uri:
            st.write("Metadata URI:")
            st.code(token_uri)

        st.markdown("**Riwayat (terbaru di atas)**")
        history = contract.functions.getHistory(int(detail_id)).call()
        st.dataframe(
            [
                {
                    "Aksi": ACTION_LABELS.get(action, action),
                    "Oleh": actor,
                    "Waktu": format_time(timestamp),
                }
                for action, actor, timestamp in history
            ],
            hide_index=True,
            width="stretch",
        )

# ---------------------------------------------------------
# BUAT BATCH (createBatch)
# ---------------------------------------------------------

with tab_create:
    if require_wallet():
        st.caption(
            "NFT rekam medis akan dimiliki oleh alamat pasien. Hanya pemilik "
            "NFT yang bisa mengubah status dan mengisi tindakan."
        )

        with st.form("create_batch"):
            patient_id = st.text_input("ID Pasien", placeholder="P-001")
            patient_name = st.text_input("Nama Pasien")
            complaint = st.text_area("Keluhan")
            patient_address = st.text_input(
                "Alamat wallet pasien", value=wallet_address
            )
            metadata_uri = st.text_input(
                "Metadata URI (opsional)", placeholder="ipfs://..."
            )
            submitted = st.form_submit_button(
                "Siapkan Transaksi", type="primary"
            )

        if submitted:
            if not Web3.is_address(patient_address):
                st.error("Alamat wallet pasien tidak valid.")
            else:
                prepare_tx(
                    "create",
                    "createBatch",
                    [
                        patient_id.strip(),
                        patient_name.strip(),
                        complaint.strip(),
                        Web3.to_checksum_address(patient_address),
                        metadata_uri.strip(),
                    ],
                    f"Buat batch untuk {patient_name.strip() or '-'}",
                )

        render_tx_area("create")

# ---------------------------------------------------------
# UPDATE STATUS (updateStatus)
# ---------------------------------------------------------

with tab_status:
    if require_wallet():
        status_id = st.number_input(
            "Token ID", min_value=1, step=1, value=1, key="status_id"
        )

        batch = get_batch(int(status_id))

        if batch is None:
            st.warning("Batch tidak ditemukan.")
        else:
            current = batch["status"]
            st.write(
                f"Pasien **{batch['patientName']}** - status saat ini: "
                f"**{status_label(current)}**"
            )

            st.progress(
                (current + 1) / len(STATUS_LABELS),
                text=f"Tahap {current + 1} dari {len(STATUS_LABELS)}",
            )

            if batch["owner"] != wallet_address:
                st.warning(
                    "Wallet Anda bukan pemilik batch ini, sehingga kontrak "
                    "akan menolak perubahan status."
                )
            elif current >= len(STATUS_LABELS) - 1:
                st.success("Rekam medis sudah selesai.")
            else:
                next_status = current + 1
                if st.button(
                    f"Ubah status ke {status_label(next_status)}",
                    type="primary",
                ):
                    prepare_tx(
                        "status",
                        "updateStatus",
                        [int(status_id), next_status],
                        f"Token {int(status_id)}: "
                        f"{status_label(next_status)}",
                    )

        render_tx_area("status")

# ---------------------------------------------------------
# TINDAKAN & OBAT (updateTreatment)
# ---------------------------------------------------------

with tab_treatment:
    if require_wallet():
        treatment_id = st.number_input(
            "Token ID", min_value=1, step=1, value=1, key="treatment_id"
        )

        batch = get_batch(int(treatment_id))

        if batch is None:
            st.warning("Batch tidak ditemukan.")
        else:
            st.write(f"Pasien **{batch['patientName']}**")

            if batch["owner"] != wallet_address:
                st.warning(
                    "Wallet Anda bukan pemilik batch ini, sehingga kontrak "
                    "akan menolak perubahan."
                )

            with st.form("update_treatment"):
                treatment = st.text_area(
                    "Tindakan", value=batch["treatment"]
                )
                medicine = st.text_area("Obat", value=batch["medicine"])
                submitted = st.form_submit_button(
                    "Siapkan Transaksi", type="primary"
                )

            if submitted:
                prepare_tx(
                    "treatment",
                    "updateTreatment",
                    [int(treatment_id), treatment.strip(), medicine.strip()],
                    f"Token {int(treatment_id)}: isi tindakan & obat",
                )

        render_tx_area("treatment")

# =========================================================
# CATATAN
# =========================================================

st.divider()

st.caption(
    "Data dibaca oleh Web3.py langsung dari Hardhat RPC. Transaksi disiapkan "
    "oleh Python lalu ditandatangani melalui MetaMask, sehingga private key "
    "tidak pernah dikirim ke aplikasi."
)
