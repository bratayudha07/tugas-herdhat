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
scripts/deploy.js               deploy + seeding peran
scripts/seed-demo.js            data demo (4 batch, tahap berbeda)
test/ehr.test.js                test kontrak
web/                            aplikasi web (FastAPI + Jinja2)
docs/                           modul, rancangan UI, rancangan kontrak
app.py                          prototipe Streamlit lama (tidak dipakai lagi)
```

## Aplikasi web (UI)

Aplikasi web untuk Pertemuan 11–12: **FastAPI + Jinja2 + Tailwind CSS +
Alpine.js**, dengan **Web3.py** sebagai penghubung chain dan **MetaMask**
sebagai penanda tangan transaksi. Semua aset pihak ketiga (Tailwind hasil
build, Alpine, ethers, font) disimpan lokal, jadi demo tetap jalan tanpa
internet.

**Status:** tahap 1 selesai — kerangka aplikasi, layout, token warna, dan
`/api/health`. Halaman lain masih placeholder dengan URL asli. Rencana per
tahap ada di `docs/Rancangan UI - EHR Traceability.md` §11.

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
| `EHR_CACHE_TTL` | `15` | umur cache pembacaan chain (detik) |
| `EHR_RPC_TIMEOUT` | `3` | timeout per request RPC (detik) |

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
