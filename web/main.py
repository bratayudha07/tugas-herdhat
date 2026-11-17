"""Aplikasi web EHR Traceability — FastAPI + Jinja2.

Jalankan dari root repo `Hardhat/`:

    uvicorn web.main:app --reload --port 8000

Fase 5: halaman Wallet & Transaksi (identitas wallet, saldo dari RPC,
riwayat transaksi sesi ini) dan Hak Akses (izin dokter per batch), plus
sapuan responsif sampai 375 px.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import chain, config, tx, view

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
        "network_label": config.network_label(),
        "path": request.url.path,
        "year": date.today().year,
        "query_url": lambda **params: _query_url(request, **params),
    }
    context.update(extra)
    return context


def _query_url(request: Request, **overrides) -> str:
    """Gabungkan query string sekarang dengan perubahan — untuk link filter.

    Filter disimpan di URL supaya bisa di-share dan tidak hilang saat refresh.
    Nilai `None`/kosong menghapus parameter.
    """
    params = dict(request.query_params)
    for key, value in overrides.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = str(value)

    return f"{request.url.path}?{urlencode(params)}" if params else request.url.path


def _page(request: Request, name: str, **extra) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=name,
        context=_context(request, **extra),
    )


# --------------------------------------------------------------------------
# Halaman
# --------------------------------------------------------------------------


def _demo_accounts() -> list[dict]:
    """Akun demo dari `deploy.js` — hanya petunjuk, bukan sumber peran."""
    accounts = config.load_deployment().get("demoAccounts", {}) or {}
    return [
        {"label": view.demo_label(key), "address": address}
        for key, address in accounts.items()
    ]


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, refresh: int = 0):
    if refresh:
        chain.refresh()

    meta = chain.contract_meta()
    batches = chain.list_batches()
    data = batches or []
    latest = sorted(data, key=lambda item: item["tokenId"], reverse=True)[:5]

    return _page(
        request,
        "dashboard.html",
        meta=meta,
        demo_accounts=_demo_accounts(),
        batches_ok=batches is not None,
        summary=view.summary(data),
        latest=latest,
    )


@app.get("/rekam-medis", response_class=HTMLResponse)
def batch_list(
    request: Request,
    q: str = "",
    status: str = "",
    doctor: str = "",
    mine: int = 0,
    wallet: str = "",
    view_mode: str = Query("kartu", alias="view"),
    refresh: int = 0,
):
    if refresh:
        chain.refresh()

    batches = chain.list_batches()
    # Urut dari token terbaru — daftar lebih sering dipakai untuk melihat
    # batch yang baru masuk.
    data = sorted(batches or [], key=lambda item: item["tokenId"], reverse=True)

    status = status.strip().upper()
    if status not in view.STATUS_ORDER:
        status = ""

    filtered = view.filter_batches(
        data,
        q=q,
        status=status,
        doctor=doctor,
        wallet=wallet,
        mine=bool(mine),
    )

    return _page(
        request,
        "batches.html",
        batches=filtered,
        total=len(data),
        batches_ok=batches is not None,
        doctors=chain.doctors(),
        filters={
            "q": q,
            "status": status,
            "doctor": doctor,
            "mine": bool(mine),
            "wallet": wallet.strip(),
        },
        filters_active=bool(
            q.strip() or status or doctor or (mine and wallet.strip())
        ),
        wallet_missing=bool(mine and not wallet.strip()),
        view_mode="tabel" if view_mode == "tabel" else "kartu",
    )


@app.get("/rekam-medis/{token_id:int}", response_class=HTMLResponse)
def batch_detail(request: Request, token_id: int, refresh: int = 0):
    """Detail batch + aksi tulis sesuai peran wallet (diselesaikan di client)."""
    if refresh:
        chain.refresh()

    batch = chain.batch_detail(token_id)
    if batch is None:
        return templates.TemplateResponse(
            request=request,
            name="batch_missing.html",
            context=_context(request, token_id=token_id),
            status_code=404,
        )

    return _page(
        request,
        "batch_detail.html",
        batch=batch,
        consent=chain.consent_of(token_id, batch["doctor"]),
        doctors=chain.doctors(),
    )


@app.get("/rekam-medis/baru", response_class=HTMLResponse)
def batch_new(request: Request, refresh: int = 0):
    """Form input batch baru — pengirimnya MetaMask, bukan server."""
    if refresh:
        chain.refresh()

    doctors = chain.doctors()
    return _page(
        request,
        "batch_new.html",
        doctors=doctors,
        doctors_ok=bool(doctors),
        total=len(chain.list_batches() or []),
    )


@app.get("/wallet", response_class=HTMLResponse)
def wallet_page(request: Request, refresh: int = 0):
    """Wallet & Transaksi: identitas wallet, saldo RPC, riwayat sesi ini."""
    if refresh:
        chain.refresh()
    return _page(request, "wallet.html", meta=chain.contract_meta())


@app.get("/hak-akses", response_class=HTMLResponse)
def access_page(request: Request, refresh: int = 0):
    """Hak Akses: izin dokter per batch, disaring sesuai peran wallet."""
    if refresh:
        chain.refresh()
    return _page(request, "hak_akses.html")


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


@app.get("/api/role")
def api_role(address: str = ""):
    """Peran satu alamat dari `getRole()` — dipakai untuk gerbang form."""
    info = chain.role_of(address)
    if info is None:
        return JSONResponse(
            {"error": "Alamat tidak valid atau kontrak belum bisa dibaca."},
            status_code=400,
        )

    info["label"] = view.role_label(info["roleIndex"])
    return JSONResponse(info)


@app.get("/api/batch/{token_id}/context")
def api_batch_context(token_id: int, address: str = ""):
    """Hak tulis wallet ini pada satu batch — dasar tombol di halaman detail."""
    try:
        info = tx.batch_context(token_id, address)
    except tx.TxError as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status)

    if info is None:
        return JSONResponse({"error": "Batch tidak ditemukan."}, status_code=404)

    return JSONResponse(info)


@app.get("/api/demo")
def api_demo():
    """Akun demo (khusus testnet): peran, saldo, dan kunci untuk dicoba.

    Kalau deployment tidak memuat `demoKeys` (mis. node lokal Hardhat), daftar
    akun tetap dikirim tanpa kunci — halaman tidak menampilkan apa pun yang
    tidak ada.
    """
    try:
        return JSONResponse(tx.demo_overview())
    except tx.TxError as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status)


@app.get("/api/account")
def api_account(address: str = ""):
    """Peran, saldo, nonce, dan harga gas satu alamat — dasar halaman Wallet."""
    try:
        return JSONResponse(tx.account_overview(address))
    except tx.TxError as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status)


@app.get("/api/access")
def api_access(address: str = ""):
    """Tabel izin per batch sesuai peran wallet (dasar halaman Hak Akses)."""
    try:
        payload = tx.access_overview(address)
    except tx.TxError as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status)

    # Daftar akun demo + perannya hanya berguna untuk admin (halaman penjelasan
    # peran). Label-nya milik lapisan halaman, jadi disusun di sini.
    # Sumbernya ringkasan demo (peran + saldo dibaca batch), bukan
    # `account_overview` per akun — versi per akun menembak RPC empat kali untuk
    # tiap akun, dan itu membuat halaman menunggu belasan detik di RPC publik.
    if payload["role"] == "ADMIN":
        try:
            ringkas = tx.demo_overview().get("accounts", [])
        except tx.TxError:
            ringkas = []

        payload["accounts"] = [
            {
                "label": row["label"],
                "address": row["address"],
                "role": row["role"],
                "roleLabel": row["roleLabel"],
                "ownedBatches": row["ownedBatches"],
                "assignedBatches": row["assignedBatches"],
            }
            for row in ringkas
        ]

    return JSONResponse(payload)


@app.post("/api/tx/build")
async def api_tx_build(request: Request):
    """Siapkan transaksi (validasi + dry-run). Tanda tangan tetap di wallet."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Body harus berupa JSON."}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"error": "Body harus objek JSON."}, status_code=400)

    try:
        result = tx.build(payload)
    except tx.TxError as exc:
        return JSONResponse(
            {"error": exc.message, "fields": exc.fields},
            status_code=exc.status,
        )

    return JSONResponse(result)


@app.get("/api/tx/{tx_hash}")
def api_tx_status(tx_hash: str):
    """Status receipt satu transaksi: pending / success / failed."""
    try:
        return JSONResponse(tx.tx_status(tx_hash))
    except tx.TxError as exc:
        return JSONResponse({"error": exc.message}, status_code=exc.status)



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
