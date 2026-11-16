"""Aplikasi web EHR Traceability — FastAPI + Jinja2.

Jalankan dari root repo `Hardhat/`:

    uvicorn web.main:app --reload --port 8000

Fase 1: kerangka + status jaringan. Halaman lain masih stub.
"""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import chain, config, view

app = FastAPI(
    title="EHR Traceability",
    description="Rekam medis pasien on-chain — UI Praktikum Blockchain 11–12",
    docs_url="/api/docs",
    redoc_url=None,
)

app.mount(
    "/static",
    StaticFiles(directory=config.STATIC_DIR),
    name="static",
)

templates = Jinja2Templates(directory=config.TEMPLATES_DIR)
view.register(templates.env)


def _context(request: Request, **extra) -> dict:
    """Konteks dasar semua halaman: status chain, navigasi, footer."""
    status = chain.health()
    context = {
        "health": status,
        "chain_label": chain.chain_label(status),
        "contract_address": status["address"],
        "rpc_url": config.RPC_URL,
        "rpc_display": config.RPC_URL.split("://")[-1],
        "path": request.url.path,
        "year": date.today().year,
    }
    context.update(extra)
    return context


def _page(request: Request, name: str, **extra) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=name,
        context=_context(request, **extra),
    )


# --------------------------------------------------------------------------
# Halaman
# --------------------------------------------------------------------------


DEMO_LABELS = {
    "admin": "Admin",
    "receptionist": "Resepsionis",
    "doctor": "Dokter",
    "doctor2": "Dokter 2",
    "patient": "Pasien",
}


def _demo_accounts() -> list[dict]:
    """Akun demo dari `deploy.js` — hanya petunjuk, bukan sumber peran."""
    accounts = config.load_deployment().get("demoAccounts", {}) or {}
    return [
        {"label": DEMO_LABELS.get(key, key.title()), "address": address}
        for key, address in accounts.items()
    ]


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, refresh: int = 0):
    if refresh:
        chain.refresh()

    meta = chain.contract_meta()

    return _page(
        request,
        "dashboard.html",
        meta=meta,
        demo_accounts=_demo_accounts(),
    )


# Stub halaman yang dibangun di fase berikutnya. Satu sumber data supaya
# sidebar, judul, dan isi placeholder tidak berbeda-beda.
STUBS: dict[str, dict] = {
    "/rekam-medis": {
        "heading": "Daftar Batch",
        "phase": 2,
        "intro": "Tabel rekam medis dari kontrak: cari, filter status, dan filter "
        "milik saya.",
        "items": [
            "Daftar batch dari <code>totalSupply()</code> + <code>getBatch()</code>",
            "Pencarian ID / nama pasien dan filter per status",
            "Tampilan tabel dan kartu, plus empty state",
        ],
    },
    "/rekam-medis/baru": {
        "heading": "Buat Batch",
        "phase": 3,
        "intro": "Form pendaftaran pasien baru dengan validasi dan pengiriman "
        "transaksi lewat MetaMask.",
        "items": [
            "Validasi field wajib + dropdown dokter dari <code>getDoctors()</code>",
            "Dry-run <code>.call()</code> sebelum tanda tangan transaksi",
            "Panel status transaksi: menunggu, berhasil, gagal (revert kontrak)",
        ],
    },
    "/wallet": {
        "heading": "Wallet & Transaksi",
        "phase": 5,
        "intro": "Alamat, jaringan, saldo, peran akun, dan status transaksi "
        "terakhir.",
        "items": [
            "Alamat wallet, chain ID, dan saldo dari <code>eth.get_balance</code>",
            "Peran akun hasil resolusi <code>getRole</code> + kepemilikan NFT",
            "Riwayat hash transaksi sesi ini",
        ],
    },
    "/hak-akses": {
        "heading": "Hak Akses",
        "phase": 5,
        "intro": "Kendali izin: pasien memberi/mencabut izin dokter, resepsionis "
        "menunjuk dokter penanggung jawab.",
        "items": [
            "Status consent per batch dan dokter",
            "Pasien: izinkan / cabut izin (hanya pemilik NFT)",
            "Resepsionis: ganti dokter penanggung jawab",
        ],
    },
}


def _stub(request: Request, path: str) -> HTMLResponse:
    return _page(request, "stub.html", stub=STUBS[path], path=path)


@app.get("/rekam-medis", response_class=HTMLResponse)
def batch_list(request: Request):
    return _stub(request, "/rekam-medis")


@app.get("/rekam-medis/baru", response_class=HTMLResponse)
def batch_new(request: Request):
    return _stub(request, "/rekam-medis/baru")


@app.get("/wallet", response_class=HTMLResponse)
def wallet(request: Request):
    return _stub(request, "/wallet")


@app.get("/hak-akses", response_class=HTMLResponse)
def access(request: Request):
    return _stub(request, "/hak-akses")


@app.get("/refresh")
def refresh_page(request: Request):
    """Bersihkan cache pembacaan chain lalu kembali ke halaman asal."""
    chain.refresh()
    return RedirectResponse(url=request.headers.get("referer") or "/", status_code=303)


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


@app.get("/api/health")
def api_health(refresh: int = 0):
    """Status RPC, chain, dan kontrak — dipakai UI & untuk cek cepat."""
    if refresh:
        chain.refresh()

    status = chain.health()
    payload = dict(status)
    payload["contractName"] = None

    meta = chain.contract_meta()
    if meta:
        payload["contractName"] = meta.get("name")
        payload["totalSupply"] = meta.get("totalSupply")
        payload["doctorCount"] = meta.get("doctorCount")

    return JSONResponse(payload)


# --------------------------------------------------------------------------
# Error handler
# --------------------------------------------------------------------------


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "Endpoint tidak ditemukan"}, status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="404.html",
        context=_context(request),
        status_code=404,
    )
