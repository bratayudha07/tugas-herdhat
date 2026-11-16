# EHR Traceability

Rekam medis pasien sebagai NFT (ERC-721) di blockchain lokal, dibangun dengan
Hardhat + Solidity + Hardhat Network. Proyek Praktikum Blockchain (EHR,
contoh *c* modul Pertemuan 11–12).

## Konsep

Setiap kunjungan pasien dicatat sebagai **batch** yang di-mint sebagai NFT
milik pasien. Hak tulis dipisahkan dari kepemilikan:

| Peran | Boleh melakukan |
|---|---|
| Admin (deployer) | memberi/mencabut peran |
| Resepsionis | membuat batch, menunjuk dokter penanggung jawab |
| Dokter (ditugaskan) | mengisi tindakan & obat, memajukan status — **setelah pasien memberi izin** |
| Pasien (pemilik NFT) | memberi/mencabut izin dokter |

Alur status: `CREATED → EXAMINED → DIAGNOSED → TREATED → COMPLETED`
(maju satu tahap per transaksi).

Catatan desain:

- NFT bersifat **soulbound** — rekam medis tidak bisa dipindahkan ke wallet lain.
- Data medis tersimpan **plaintext** di chain lokal. Consent mengatur izin
  **menulis**, bukan kerahasiaan baca.
- Rekam medis yang sudah `COMPLETED` tidak bisa diubah lagi.

## Prasyarat

- Node.js + npm
- MetaMask (untuk demo transaksi dari browser)

## Menjalankan

```bash
npm install

# terminal 1: jalankan node lokal
npx hardhat node

# terminal 2: deploy + beri peran otomatis
npx hardhat run scripts/deploy.js --network localhost

# opsional: isi 4 batch contoh untuk demo
npx hardhat run scripts/seed-demo.js --network localhost
```

`deploy.js` menulis `deployment.json` berisi alamat kontrak dan akun demo.
Peran admin/resepsionis/dokter tercatat di sana dan bisa diverifikasi
on-chain lewat `getRole()`.

### Akun demo (Hardhat default)

| Peran | Alamat |
|---|---|
| Admin (#0) | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` |
| Resepsionis (#1) | `0x70997970C51812dc3A010C7d01b50e0d17dc79C8` |
| Dokter (#2) | `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC` |
| Dokter 2 (#3) | `0x90F79bf6EB2c4f870365E785982E1f101E93b906` |
| Pasien (#4) | `0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65` |

Impor private key akun-akun ini ke MetaMask (private key tercetak saat
`npx hardhat node` berjalan) dan tambahkan jaringan
`Hardhat Local` → `http://127.0.0.1:8545`, chain ID `31337`.

## Test

```bash
npx hardhat test
```

20 test kontrak (`test/ehr.test.js`) mencakup pembatasan peran, consent,
soulbound, ganti dokter, dan aturan status.

## Struktur

```
contracts/EHRTraceability.sol   kontrak utama
scripts/deploy.js               deploy + seeding peran (lokal & testnet)
scripts/seed-demo.js            data demo (4 batch, tahap berbeda)
scripts/lib/deployment.js       helper: file deployment & signer per jaringan
scripts/export-abi.js           salin ABI ke web/abi.json (untuk hosting)
test/ehr.test.js                test kontrak
app.py                          entrypoint ASGI (jembatan ke web/main.py)
web/                            aplikasi web (FastAPI + Jinja2)
docs/                           modul, rancangan UI, rancangan kontrak
legacy/app_streamlit.py         prototipe Streamlit lama (tidak dipakai)
```

## Aplikasi web (UI)

Aplikasi web untuk Pertemuan 11–12: **FastAPI + Jinja2 + Tailwind CSS +
Alpine.js**, dengan **Web3.py** sebagai penghubung chain dan **MetaMask**
sebagai penanda tangan transaksi. Semua aset pihak ketiga (Tailwind hasil
build, Alpine, ethers, font) disimpan lokal, jadi demo tetap jalan tanpa
internet.

**Status:** tahap 1–5 selesai — semua halaman modul sudah berfungsi: kerangka
+ `/api/health`, dashboard dan daftar batch read-only, form **Buat Batch**,
**aksi tulis di detail batch** (majukan status, simpan tindakan/obat, izin
pasien, ganti dokter), serta **Wallet & Transaksi** dan **Hak Akses**. Semua
transaksi ditandatangani MetaMask (validasi + dry-run di server, calldata
dikirim balik ke browser). Tata letak diuji sampai 375 px. Rencana per tahap
ada di `docs/Rancangan UI - EHR Traceability.md` §11.

- `/wallet` — alamat wallet, peran efektif (`getRole()` + kepemilikan NFT),
  saldo/nonce/harga gas dari RPC lewat Web3.py, tombol salin/ganti akun,
  dan riwayat transaksi sesi ini (`localStorage`, hanya yang ber-hash).
- `/hak-akses` — izin dokter per batch, disaring sesuai peran: pasien
  memberi/mencabut izin batch miliknya, dokter melihat status penugasan,
  resepsionis mendapat tautan ganti dokter, admin melihat tabel akun demo.

Hak tulis mengikuti kontrak apa adanya: dokter harus berperan **DOKTER**,
tercatat sebagai dokter penanggung jawab batch, dan sudah diberi izin pasien;
resepsionis hanya bisa mengganti dokter; pasien pemilik NFT memberi/mencabut
izin. Hak itu dibaca ulang dari chain tiap akun berganti, jadi tombol yang
tampil tidak pernah menawarkan transaksi yang pasti revert.

Syarat demo: wallet MetaMask di chain 31337 dengan akun hasil
`scripts/deploy.js` (resepsionis, dokter, pasien). Server tidak pernah
memegang private key — ia hanya menyiapkan `to` + `data`.

### Menjalankan

```bash
# 1. dependency Python (sekali saja)
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# kalau .venv dibuat dengan uv (tidak ada pip di dalamnya):
# uv pip install --python .venv/bin/python -r requirements.txt

# 2. node + deploy (dua terminal terpisah)
npx hardhat node
npx hardhat run scripts/deploy.js --network localhost
npx hardhat run scripts/seed-demo.js --network localhost   # opsional

# 3. aplikasi web
.venv/bin/python -m uvicorn web.main:app --reload --port 8000
```

Buka <http://127.0.0.1:8000>. Cek cepat status jaringan:
<http://127.0.0.1:8000/api/health>.

Variabel lingkungan yang dibaca aplikasi:

| Variabel | Default | Guna |
|---|---|---|
| `EHR_RPC_URL` | `http://127.0.0.1:8545` | alamat RPC Hardhat |
| `EHR_DEPLOYMENT_PATH` | `deployment.json` | file alamat kontrak + akun demo (mis. `deployment.sepolia.json`) |
| `EHR_CACHE_TTL` | `15` | umur cache pembacaan chain (detik) |
| `EHR_RPC_TIMEOUT` | `3` | timeout per request RPC (detik) |

### Deploy online (Vercel + Sepolia)

GitHub Pages **tidak cukup** untuk aplikasi ini: halaman dirender Jinja2 dan
data dibaca lewat Web3.py, jadi harus ada proses Python. Yang dipakai:
**Vercel** (menjalankan FastAPI sebagai Vercel Function) untuk aplikasi, dan
**Sepolia** sebagai chain publik karena node Hardhat lokal tidak bisa diakses
dari internet.

Alur lengkapnya:

```bash
# 1. Buat akun demo testnet. Skrip berhenti kalau saldo admin masih 0.
npm run deploy:sepolia
#    → salin alamat "admin (deployer)" ke faucet Sepolia, lalu ulangi perintah
npm run deploy:sepolia

# 2. Isi data demo (4 batch, tahap berbeda)
npm run seed:sepolia
```

Hasilnya: `deployment.sepolia.json` berisi alamat kontrak, peran, dan
**private key akun demo** — kunci itu memang ditampilkan di halaman Wallet
supaya pengunjung bisa mengimpor akun ke MetaMask dan mencoba tombol tulis.
Konsekuensinya: bot testnet suka menyapu saldo akun yang kuncinya publik.
Saldo akun demo bisa habis kapan saja; isi ulang dari faucet saat mau demo.
Jangan pernah memakai pola ini untuk akun bernilai nyata.

Setelah repo ada di GitHub, buat project di Vercel (import repo, framework
terdeteksi otomatis sebagai FastAPI lewat `app.py` + `requirements.txt`), lalu
set environment variable:

| Variabel | Nilai |
|---|---|
| `EHR_RPC_URL` | RPC Sepolia ber-API-key (Alchemy/Infura). Endpoint publik tanpa key bisa, tapi dipakai bersama dan mudah kena `429` |
| `EHR_DEPLOYMENT_PATH` | `deployment.sepolia.json` |
| `EHR_CACHE_TTL` | `30` (opsional; serverless tanpa cache persisten) |

Catatan penting untuk hosting:

- `artifacts/` tidak ikut ter-commit, jadi ABI dibaca dari `web/abi.json`.
  Setelah kontrak berubah, jalankan `npx hardhat compile && npm run abi`.
- Server tidak menulis file apa pun, jadi filesystem read-only Vercel aman.
- Cache pembacaan chain ada di memori proses; instance baru mulai dingin.
  Dengan 4 batch, satu halaman tetap terasa cepat (~1 detik setelah warm).

### Endpoint API internal

| Endpoint | Guna |
|---|---|
| `GET /api/health` | status RPC, chain, blok, kontrak, `totalSupply` |
| `GET /api/role?address=0x…` | peran satu alamat dari `getRole()` |
| `GET /api/account?address=0x…` | peran efektif, saldo, nonce, harga gas, jumlah batch milik/ditugaskan |
| `GET /api/access?address=0x…` | tabel izin per batch sesuai peran (+ tabel akun demo untuk admin) |
| `GET /api/demo` | akun demo testnet: peran, saldo, dan private key yang sengaja dibagikan |
| `GET /api/batch/{id}/context?address=0x…` | hak tulis satu wallet pada batch (dasar tombol di halaman detail) |
| `POST /api/tx/build` | validasi + dry-run + calldata siap tanda tangan |
| `GET /api/tx/{hash}` | status receipt: `pending` / `success` / `failed` |
| `GET /api/docs` | dokumentasi otomatis FastAPI |

Contoh `POST /api/tx/build`:

```json
{ "action": "createBatch", "from": "0x7099…", "args": {
    "patientId": "P-001", "patientName": "Budi Santoso",
    "complaint": "demam 3 hari", "patient": "0x15d3…",
    "doctor": "0x3C44…", "metadata": "" } }
```

Balasannya `{ "to": …, "data": "0x…", "label": …, "summary": […],
"predictedTokenId": 5 }` — `summary` adalah daftar `{label, value}` yang
ditampilkan di dialog konfirmasi, jadi teks transaksi tidak disusun ulang di
JavaScript. Kalau ditolak: `400` + `{ "error": "Hanya resepsionis", "fields": {} }`
— alasan revert kontrak ditampilkan apa adanya.

`action` yang dikenal: `createBatch`, `updateStatus`, `updateTreatment`,
`setConsent`, `assignDoctor`. Semuanya memakai bentuk payload yang sama
(`from` + `args`), dan server selalu menjalankan dry-run dulu supaya
transaksi yang pasti revert tidak sampai ditandatangani.

### Mengubah CSS

`web/static/css/app.css` adalah **hasil build** dari
`web/static/css/input.css` + `web/tailwind.config.js`. Kalau mengubah class
Tailwind di template atau menambah komponen:

```bash
# Tailwind CLI standalone (tanpa Node), sekali unduh
tailwindcss -c web/tailwind.config.js -i web/static/css/input.css \
  -o web/static/css/app.css --minify
```

Commit `app.css` ikut, karena browser memakainya langsung.

`app.py` adalah prototipe Streamlit lama dan **tidak kompatibel** dengan
kontrak versi peran & consent (signature `createBatch` berubah).
