# EHR Traceability

Aplikasi rekam medis pasien berbasis blockchain. Setiap batch rekam medis disimpan sebagai NFT soulbound (tidak bisa dipindahkan), dan hanya dokter yang ditugaskan serta sudah diizinkan pasien yang bisa mengubah data. Semua aksi tercatat di blockchain sebagai riwayat.

**Teknologi:** Solidity + Hardhat, Web3.py, FastAPI + Jinja2, Tailwind CSS, MetaMask.

## Identitas Kelompok

**Kelompok 6 — Praktikum Blockchain**

| Nama | NIM |
|---|---|
| Hafidzar Ashyawal Sinatryas | 2530801075 |
| Haidar | 2530801079 |
| Robbi Hamdi | 2530801057 |

## Cara Menjalankan

Prasyarat: Node.js 18+, Python 3.11+, dan ekstensi MetaMask di browser.

```bash
# Clone repo
git clone https://github.com/bratayudha07/tugas-herdhat.git
cd tugas-herdhat

# Install dependency
npm install
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Lalu jalankan di **tiga terminal**:

```bash
# Terminal 1 — node blockchain lokal (biarkan tetap hidup)
npx hardhat node

# Terminal 2 — deploy kontrak + isi data demo
npm run deploy:local
npm run seed:local

# Terminal 3 — aplikasi web
.venv/bin/python -m uvicorn web.main:app --port 8000
```

Buka **http://127.0.0.1:8000**.

### Setup MetaMask

1. Tambah jaringan: RPC `http://127.0.0.1:8545`, Chain ID `31337`, simbol ETH.
2. Import akun dari private key yang dicetak `npx hardhat node`, misalnya akun #1 untuk resepsionis, #2 untuk dokter, #4 untuk pasien.
3. Kalau node Hardhat di-restart, jalankan ulang `npm run deploy:local` dan `npm run seed:local`.

## Catatan

- Data pasien yang dipakai adalah data dummy.
- Data medis tersimpan plaintext di blockchain, jadi bisa dibaca siapa pun. Izin pasien (`consent`) mengatur hak **menulis**, bukan kerahasiaan data.
- Proyek ini dibuat untuk keperluan tugas kuliah.
