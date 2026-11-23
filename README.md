# EHR Traceability — Rekam Medis Pasien Berbasis Blockchain

Aplikasi pencatatan rekam medis pasien di mana **setiap batch rekam medis disimpan sebagai NFT soulbound** di blockchain, dan setiap perubahan data hanya bisa dilakukan oleh pihak yang punya peran, ditugaskan pada batch tersebut, **dan** sudah diizinkan oleh pasien. Semua aksi tercatat permanen sebagai riwayat (audit trail) di dalam kontrak.

Dibuat untuk tugas Praktikum Blockchain (Pertemuan 11–12: Implementasi UI). Data yang dipakai adalah data dummy.

---

## Fitur Utama

- **Rekam medis sebagai NFT (ERC-721) soulbound** — tidak bisa dipindahkan atau diperjualbelikan.
- **Kontrol akses berlapis** — hak tulis = peran (`DOCTOR`) + dokter penanggung jawab batch + izin (`consent`) dari pasien.
- **Persetujuan pasien** — pasien memberi/mencabut izin dokter langsung dari UI; ganti dokter otomatis mencabut izin dokter lama.
- **Audit trail on-chain** — riwayat aksi (`BATCH_CREATED`, `CONSENT_GRANTED`, `STATUS_UPDATED`, dst.) disimpan di kontrak dan ditampilkan terbaru di atas.
- **Alur status bertahap** — `CREATED → EXAMINED → DIAGNOSED → TREATED → COMPLETED`, wajib maju satu langkah; batch `COMPLETED` terkunci.
- **UI server-rendered** — dashboard, daftar + filter, form input bervalidasi, detail batch, wallet, dan hak akses. Semua tombol tulis hanya muncul kalau wallet-nya memang berhak.
- **Transaksi lewat MetaMask** — server hanya menyiapkan `to` + `data` (setelah dry-run `.call`), private key tidak pernah menyentuh server.

---

## Teknologi

| Lapisan | Dipakai |
|---|---|
| Smart contract | Solidity `0.8.28` + OpenZeppelin `ERC721URIStorage` |
| Development chain | Hardhat 2 + Hardhat Toolbox (Chai test) |
| Backend | FastAPI + Uvicorn (Python 3.11+) |
| Baca/tulis chain | Web3.py 8 |
| Template | Jinja2 |
| Styling | Tailwind CSS 3 (hasil build di-commit, tanpa Node saat runtime) |
| Interaksi klien | Alpine.js 3 + ethers.js 6 (MetaMask `BrowserProvider`) |
| Jaringan | Hardhat Local (chain ID `31337`) untuk demo, Sepolia untuk testnet publik |

Kontrak: `contracts/EHRTraceability.sol` — NFT `name()` = **EHR Traceability**, symbol **EHR**.

---

## Peran & Hak Akses

| Peran | Bisa melakukan |
|---|---|
| `ADMIN` | `setRole()` — memberi/mencabut peran akun lain (deployer otomatis admin) |
| `RECEPTIONIST` | `createBatch()` (mint NFT ke pasien), `assignDoctor()` |
| `DOCTOR` | `updateStatus()`, `updateTreatment()` — **hanya** untuk batch yang ditugaskan kepadanya **dan** yang sudah diizinkan pasien |
| Pasien (pemilik NFT) | `setConsent()` — memberi/mencabut izin dokter penanggung jawab |
| Tanpa peran | baca data saja |

Catatan jujur soal desain:

- `consent` mengatur izin **menulis**, bukan kerahasiaan baca. Data medis tersimpan plaintext on-chain, jadi siapa pun yang membaca chain tetap bisa melihatnya.
- ID pasien **tidak** divalidasi unik oleh kontrak; form hanya memperingatkan.
- Batch `COMPLETED` tidak bisa diubah lagi (termasuk izin).

---

## Halaman Aplikasi

| Halaman | URL | Isi |
|---|---|---|
| Dashboard | `/` | status RPC/chain/kontrak, jumlah batch & pasien, distribusi status, batch terbaru |
| Daftar Batch | `/rekam-medis` | semua batch, cari (nama/ID/token), filter status & dokter, filter "milik saya", mode kartu/tabel |
| Buat Batch | `/rekam-medis/baru` | form `createBatch` dengan validasi server + kirim via MetaMask (khusus resepsionis) |
| Detail Batch | `/rekam-medis/{tokenId}` | stepper status, data medis, NFT & penugasan, riwayat, aksi sesuai peran wallet |
| Wallet & Transaksi | `/wallet` | alamat, jaringan, saldo, nonce, harga gas, riwayat transaksi sesi ini |
| Hak Akses | `/hak-akses` | tabel izin dokter per batch, disaring sesuai peran wallet |

Dokumentasi API otomatis tersedia di `/api/docs` saat aplikasi jalan.

Endpoint utama: `GET /api/health`, `GET /api/role`, `GET /api/batch/{id}/context`, `GET /api/account`, `GET /api/access`, `POST /api/tx/build`, `GET /api/tx/{hash}`.

---

## Alur Penggunaan

1. **Resepsionis** membuka **Buat Batch**, mengisi ID/nama pasien, keluhan, dan memilih dokter dari daftar on-chain (`getDoctors()`), lalu menandatangani transaksi di MetaMask. NFT rekam medis ter-mint ke wallet pasien.
2. **Pasien** membuka **Hak Akses** (atau detail batch) dan menekan **Izinkan dokter**. Tanpa langkah ini dokter tidak bisa menulis apa pun.
3. **Dokter** membuka **Detail Batch**: memajukan status satu tahap, mengisi tindakan & obat. Tombolnya hanya muncul kalau wallet-nya dokter penanggung jawab dan izinnya aktif.
4. **Resepsionis** bisa mengganti dokter penanggung jawab (`assignDoctor`) — izin dokter lama otomatis dicabut dan pasien perlu menyetujui dokter baru.
5. **Semua pihak** bisa memantau status jaringan, saldo, dan transaksi di **Wallet & Transaksi**, serta memfilter data di **Daftar Batch**.

---

## Struktur Folder

```
Hardhat/
├── contracts/
│   ├── EHRTraceability.sol      # kontrak utama (NFT soulbound + peran + consent)
│   └── Lock.sol                 # bawaan template Hardhat, tidak dipakai
├── scripts/
│   ├── deploy.js                # deploy + set peran + tulis deployment.json
│   ├── seed-demo.js             # isi 4 batch demo (idempoten, aman diulang)
│   ├── export-abi.js            # artifacts → web/abi.json
│   └── lib/deployment.js        # helper path & akun demo per jaringan
├── test/
│   ├── ehr.test.js              # test peran, consent, status, soulbound
│   └── Lock.js                  # test bawaan template
├── web/
│   ├── main.py                  # route FastAPI (halaman + API)
│   ├── config.py                # path, ABI, alamat kontrak, RPC, env var
│   ├── chain.py                 # baca chain via Web3.py + cache 15 detik
│   ├── tx.py                    # validasi → dry-run → calldata, baca receipt
│   ├── validate.py              # aturan form (satu sumber kebenaran)
│   ├── view.py                  # label, format ETH/tanggal, filter
│   ├── abi.json                 # salinan ABI (untuk hosting tanpa artifacts/)
│   ├── templates/               # base, dashboard, batches, batch_detail, ...
│   ├── static/
│   │   ├── css/app.css          # hasil build Tailwind (di-commit)
│   │   ├── js/{wallet,tx,api,account}.js
│   │   ├── fonts/               # Figtree, Noto Sans, JetBrains Mono
│   │   └── vendor/              # alpine.min.js, ethers.umd.min.js
│   └── tailwind.config.js
├── docs/                        # rancangan UI, rancangan kontrak, modul
├── legacy/app_streamlit.py      # prototipe Streamlit lama (tidak dipakai)
├── app.py                       # entrypoint ASGI untuk hosting (mis. Vercel)
├── deployment.json              # alamat kontrak + akun demo (lokal)
├── deployment.sepolia.json      # alamat kontrak + akun demo (Sepolia)
├── hardhat.config.js
├── requirements.txt
└── README.md
```

---

## Prasyarat

- Node.js 18+ dan npm
- Python 3.11+ (dites dengan 3.14)
- MetaMask (atau wallet lain yang mendukung `window.ethereum`)

---

## Instalasi dan Menjalankan (Lokal)

```bash
# 1. Clone repository
git clone https://github.com/bratayudha07/tugas-herdhat.git
cd tugas-herdhat

# 2. Dependency kontrak & Hardhat
npm install

# 3. Dependency Python
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Jalankan di **tiga terminal** (urutannya penting):

```bash
# Terminal 1 — node blockchain lokal (biarkan tetap hidup)
npx hardhat node

# Terminal 2 — deploy kontrak + isi data demo
npm run deploy:local
npm run seed:local

# Terminal 3 — aplikasi web
.venv/bin/python -m uvicorn web.main:app --reload --port 8000
```

Buka **http://127.0.0.1:8000**.

> `npm run deploy:local` mengubah `deployment.json` (alamat kontrak + akun demo). `seed:local` mengisi 4 batch dengan tahap berbeda, termasuk satu batch yang izinnya **sengaja belum diberikan** untuk mendemokan dokter yang terblokir. Seed cocok berdasarkan `patientId`, jadi aman dijalankan ulang.

### Menyiapkan MetaMask

1. Tambahkan jaringan baru: RPC `http://127.0.0.1:8545`, Chain ID `31337`, simbol ETH.
2. Import akun dari private key yang **dicetak `npx hardhat node`** (akun #0 = admin/deployer, #1 = resepsionis, #2–#3 = dokter, #4–#7 = pasien).
3. Kalau node Hardhat di-restart, seluruh state chain hilang — jalankan ulang `deploy:local` + `seed:local` dan reset akun MetaMask (*Settings → Advanced → Clear activity tab data*).

### Perintah npm yang tersedia

| Perintah | Fungsi |
|---|---|
| `npx hardhat node` | jalankan node lokal |
| `npm run deploy:local` | deploy kontrak + set peran ke node lokal |
| `npm run seed:local` | isi data demo ke node lokal |
| `npm run deploy:sepolia` | deploy ke Sepolia |
| `npm run seed:sepolia` | isi data demo ke Sepolia |
| `npx hardhat test` | jalankan test kontrak |
| `npm run abi` | salin ABI dari `artifacts/` ke `web/abi.json` |

`npm run abi` hanya perlu dijalankan setelah `EHRTraceability.sol` berubah (butuh `npx hardhat compile` lebih dulu). Untuk development lokal, aplikasi membaca ABI langsung dari `artifacts/`.

---

## Deploy ke Sepolia (opsional)

```bash
# RPC publik default; override kalau punya endpoint Alchemy/Infura
export SEPOLIA_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/API_KEY"

npm run deploy:sepolia   # jalankan sekali: skrip membuat akun demo & minta faucet
npm run seed:sepolia     # jalankan lagi setelah akun admin punya saldo
```

Arahkan aplikasi ke hasil deploy Sepolia dengan env var:

```bash
EHR_DEPLOYMENT_PATH=deployment.sepolia.json \
EHR_RPC_URL="https://ethereum-sepolia-rpc.publicnode.com" \
.venv/bin/python -m uvicorn web.main:app --port 8000
```

> `deployment.sepolia.json` memuat **private key akun demo secara sengaja** supaya pengunjung bisa mengimpor akun demo ke MetaMask dan mencoba tombol tulis. Akun ini hanya untuk testnet, saldonya kosong secara nilai, dan pola ini **tidak boleh** dipakai di mainnet.

### Variabel lingkungan aplikasi web

| Variabel | Default | Fungsi |
|---|---|---|
| `EHR_RPC_URL` | `http://127.0.0.1:8545` | endpoint RPC yang dibaca server |
| `EHR_DEPLOYMENT_PATH` | `deployment.json` | file alamat kontrak + akun demo |
| `EHR_CACHE_TTL` | `15` | umur cache pembacaan chain (detik) |
| `EHR_RPC_TIMEOUT` | `3` | timeout tiap request RPC (detik) |

---

## Pengujian

```bash
npx hardhat test
```

Hasil saat ini: **29 test lulus** (kontrak `EHRTraceability` + `Lock`), mencakup:

- hanya admin yang bisa memberi peran, admin tidak bisa mengubah perannya sendiri;
- hanya resepsionis yang bisa membuat batch dan mengganti dokter;
- dokter tidak bisa menulis tanpa izin pasien, dokter lain tidak bisa menulis, resepsionis tidak punya hak tulis klinis;
- status wajib maju satu tahap dan terkunci setelah `COMPLETED`;
- NFT soulbound: `transferFrom`/`safeTransferFrom` ditolak;
- ganti dokter mencabut izin dokter lama;
- pencabutan peran dokter ikut membersihkan daftar `getDoctors()`.

---

## Screenshot & Video Demo

Belum dilampirkan di repo ini. Rincian tangkapan layar dan skrip video yang disarankan ada di `docs/Rancangan UI - EHR Traceability.md` (bagian 12). Kalau mau ditempel di README, simpan file di `docs/` lalu tambahkan tabel seperti ini:

| Halaman | File |
|---|---|
| Dashboard | `docs/01-dashboard.png` |
| Daftar Batch (filter aktif) | `docs/02-daftar-batch.png` |
| Form Buat Batch (error validasi) | `docs/03-form-validasi.png` |
| Detail Batch | `docs/04-detail-batch.png` |
| Wallet & Transaksi | `docs/05-wallet.png` |
| Hak Akses | `docs/06-hak-akses.png` |

---

## Anggota Kelompok

| Nama | NIM | Peran |
|---|---|---|
| _(isi nama)_ | _(isi NIM)_ | _(isi peran)_ |
| _(isi nama)_ | _(isi NIM)_ | _(isi peran)_ |

---

## Catatan

- Proyek ini dibuat untuk keperluan tugas/pembelajaran. Semua data pasien adalah data dummy.
- `Lock.sol`, `test/Lock.js`, dan `legacy/app_streamlit.py` adalah sisa template/prototipe lama dan tidak dipakai aplikasi.
- `app.py` di root hanya jembatan ASGI untuk platform hosting yang mencari `app` di root (mis. Vercel); logika aplikasi tetap di `web/main.py`.
- Dokumentasi desain ada di `docs/`: `Rancangan UI - EHR Traceability.md`, `Rancangan Smart Contract - Peran & Consent.md`, dan modul praktikum.
- Lisensi: ISC (lihat `package.json`).
