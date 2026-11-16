---
type: design-doc
project: EHR Traceability (Praktikum Blockchain Pertemuan 11–12)
status: fase 1–3 selesai (status jaringan, dashboard, daftar batch, form Buat Batch), fase 4–5 jalan
last_updated: 2026-11-16
---

# Rancangan UI — EHR Traceability

Dokumen ini rancangan UI untuk tugas **Pertemuan 11–12: Implementasi UI**.
Isinya keputusan desain, struktur halaman, pemetaan ke smart contract, dan
rencana kerja. Status: **fase 1–3 sudah jalan** (kerangka FastAPI + layout +
`/api/health`, dashboard + daftar batch read-only, lalu form Buat Batch yang
mengirim transaksi lewat MetaMask), fase 4–5 menyusul. `contracts/*.sol`
tidak disentuh lagi
sejak rancangan kontrak diterapkan.

---

## 1. Konteks

**Modul** mewajibkan minimal 5 jenis halaman: Dashboard, Data Management,
Form Input, Detail Data, Wallet & Transaction — plus interaksi nyata ke
smart contract lewat **Web3.py**, validasi form, dan status transaksi.

**Kontrak** (`contracts/EHRTraceability.sol`) — versi sekarang sudah memakai
peran & consent sesuai rancangan di
`docs/Rancangan Smart Contract - Peran & Consent.md`:

| Fungsi | Jenis | Akses | Keterangan |
|---|---|---|---|
| `setRole(account, role)` | write | ADMIN | kelola peran (NONE/RECEPTIONIST/DOCTOR/ADMIN) |
| `createBatch(patientId, patientName, complaint, patient, doctor, metadataURI)` | write | RESEPSIONIS | mint NFT ke pasien, simpan `createdBy` + `doctor` |
| `assignDoctor(tokenId, doctor)` | write | RESEPSIONIS | ganti dokter, consent lama dicabut |
| `setConsent(tokenId, bool)` | write | pasien (pemilik NFT) | beri/cabut izin dokter penanggung jawab |
| `updateStatus(tokenId, newStatus)` | write | dokter ditugaskan + consent | status **wajib maju satu tahap** |
| `updateTreatment(tokenId, treatment, medicine)` | write | dokter ditugaskan + consent | ditolak jika `COMPLETED` |
| `getBatch(tokenId)` | read | publik | struct `PatientBatch` (termasuk `createdBy`, `doctor`, `patient`) |
| `getHistory(tokenId)` | read | publik | riwayat aksi, urut **terbaru dulu** |
| `totalSupply()` | read | publik | jumlah batch (pengganti pembacaan event) |
| `getDoctors()` | read | publik | daftar dokter terdaftar (dropdown form) |
| `getRole(address)` / `consent(tokenId, doctor)` | read | publik | peran akun & status izin |
| `ownerOf` / `getBatchOwner` / `tokenURI` / `name` / `symbol` | read | publik | data ERC-721 |

Enum status: `CREATED → EXAMINED → DIAGNOSED → TREATED → COMPLETED`.
NFT bersifat **soulbound** (tidak bisa ditransfer).

**Yang perlu diketahui jujur soal kontrak** (mempengaruhi desain):
- Hak tulis = peran **dan** penugasan **dan** consent pasien. Jadi halaman
  "Hak Akses" punya aksi nyata, bukan hiasan.
- Data medis tersimpan plaintext on-chain. `consent` mengatur izin
  **menulis**, bukan kerahasiaan baca — jangan diklaim sebagai privasi.
- Daftar batch bisa diambil dari `totalSupply()` + `getBatch()`; tidak perlu
  memantau event (lebih cepat dan tahan restart node).
- Tidak ada validasi ID pasien unik di on-chain. Form boleh memperingatkan,
  tapi tidak boleh mengklaim "ID sudah dipakai" tanpa bukti.

### Kenapa tidak Streamlit lagi

Streamlit cepat untuk prototipe, tapi layout-nya kolom-tab dan sulit dibuat
terasa seperti aplikasi (navigasi, detail per-ID, dialog konfirmasi). Untuk
tugas ini UI-nya ikut dinilai, jadi pindah ke web app biasa.

---

## 2. Stack yang dipakai

| Lapisan | Pilihan | Alasan |
|---|---|---|
| Backend | **FastAPI + Uvicorn** | async, ringan, auto-reload, dokumentasi API gratis |
| Blockchain | **Web3.py 8** (sudah terpasang) | **wajib modul**; dipakai untuk baca data + simulasi transaksi |
| Template | **Jinja2** (bawaan FastAPI) | server-rendered, detail per-ID bisa jadi URL asli |
| Styling | **Tailwind CSS 3** (CLI standalone, hasil build di-commit) | modern, CSS akhir cuma ~16 KB, tanpa Node & tanpa kompilasi di browser |
| Interaksi | **Alpine.js 3** | dialog, filter, state wallet — cukup 15 baris per komponen |
| Wallet | **ethers.js 6 (UMD, BrowserProvider)** | MetaMask tanda tangan transaksi; private key tidak pernah ke server |
| Grafik | **CSS bar chart** (tanpa library) | 5 kategori, label langsung, ringan untuk laptop low-spec |

**Tanpa Node/npm.** Tailwind dijalankan sekali sebagai binary standalone
untuk menghasilkan `web/static/css/app.css`, lalu hasil build di-commit — jadi
browser hanya memuat CSS statis (bukan JIT Tailwind seperti Play CDN yang
berat di laptop low-spec). Alpine, ethers, dan font juga di-*vendor*/self-host
supaya demo tetap jalan walau internet mati.

Font yang dipakai: **Figtree** 500/600/700, **Noto Sans** 400/500/700,
**JetBrains Mono** 400/500 — subset latin (total ±232 KB woff2).

Kalau nanti mau lebih "SPA", jalur upgrade-nya React + Vite + API yang sama —
tapi itu butuh Node, dua proses, dan waktu setup lebih lama. Untuk tugas ini
Jinja + Alpine sudah cukup dan jauh lebih gampang dirawat.

### Struktur file yang dituju

```
Hardhat/
├─ contracts/            # JANGAN diubah
├─ artifacts/            # ABI sumber kebenaran
├─ deployment.json       # alamat kontrak hasil deploy
├─ web/
│  ├─ main.py            # FastAPI app, daftar route
│  ├─ config.py          # path, ABI, alamat kontrak, RPC, TTL cache
│  ├─ chain.py           # Web3 provider, kontrak, cache ringan
│  ├─ tx.py              # build calldata, simulasi, baca receipt
│  ├─ view.py            # label status, format ETH/waktu, short address
│  ├─ templates/
│  │  ├─ base.html       # shell: sidebar, topbar, wallet chip, toast
│  │  ├─ partials/       # status_badge, stepper, empty_state, tx_panel
│  │  ├─ dashboard.html
│  │  ├─ patients.html
│  │  ├─ patient_detail.html
│  │  ├─ patient_new.html
│  │  ├─ wallet.html
│  │  └─ access.html
│  ├─ tailwind.config.js # tema (warna → CSS variable)
│  └─ static/
│     ├─ css/input.css   # sumber Tailwind + token + komponen
│     ├─ css/app.css     # HASIL BUILD, ikut di-commit
│     ├─ fonts/          # woff2 self-hosted (Figtree/Noto Sans/JetBrains)
│     ├─ js/wallet.js    # koneksi MetaMask (alamat, chain, saldo)
│     ├─ js/tx.js        # kirim tx + polling status (fase 3)
│     └─ vendor/         # alpine.min.js, ethers.umd.min.js
└─ app.py                # Streamlit lama: simpan dulu sebagai referensi
```

---

## 3. Arah desain

Hasil `ui-ux-pro-max` untuk product *Patient Portal / Health Records*:
**Minimalism & Swiss Style + Accessible & Ethical**, palet *clinical blue +
health green*, tipografi *medical, clean, trustworthy*. Cocok: UI tugas ini
harus terbaca sebagai alat medis, bukan startup kripto.

Dials yang dipakai: **variance 3** (rata, tenang, bukan asimetris),
**motion 2** (hanya hover & transisi status), **density 7** (padat untuk
tabel/stepper, tidak sesak).

Anti-pattern yang dihindari: neon kripto, gradient ungu/pink, animasi
scroll-reveal, emoji sebagai ikon.

### Token warna

| Token | Light | Dark | Pakai untuk |
|---|---|---|---|
| `--bg` | `#FFFFFF` | `#0B1220` | latar halaman |
| `--surface` | `#F8FAFC` | `#111827` | sidebar, header tabel |
| `--card` | `#FFFFFF` | `#111827` | kartu |
| `--border` | `#E2E8F0` | `#1F2937` | garis kartu/tabel |
| `--border-strong` | `#CBD5E1` | `#334155` | border input (non-text 3:1) |
| `--text` | `#0F172A` | `#E5E7EB` | teks utama |
| `--text-muted` | `#475569` | `#94A3B8` | label, caption |
| `--primary` | `#0891B2` | `#22D3EE` | aksen, link, focus ring |
| `--primary-strong` | `#0E7490` | `#22D3EE` | tombol solid |
| `--on-primary` | `#FFFFFF` | `#0F172A` | teks di tombol |
| `--success` | `#047857` | `#34D399` | transaksi sukses |
| `--danger` | `#B91C1C` | `#F87171` | gagal/revert |
| `--warning` | `#B45309` | `#FBBF24` | jaringan salah, tx menunggu |

Kontras yang sudah dicek: teks utama ≥ 15:1, teks muted ≥ 7:1, tombol
`--primary-strong` + putih = 5,3:1. Jangan pakai `--primary` dengan teks
putih (cuma 3,7:1 — gagal untuk teks kecil).

### Warna status (selalu disertai label teks)

| Status | Badge light | Badge dark |
|---|---|---|
| CREATED | abu `#F1F5F9` / teks `#334155` | `#1F2937` / `#E5E7EB` |
| EXAMINED | biru `#DBEAFE` / `#1D4ED8` | `#1E3A8A` / `#DBEAFE` |
| DIAGNOSED | violet `#EDE9FE` / `#6D28D9` | `#3730A3` / `#E0E7FF` |
| TREATED | amber `#FEF3C7` / `#B45309` | `#78350F` / `#FDE68A` |
| COMPLETED | hijau `#D1FAE5` / `#047857` | `#064E3B` / `#A7F3D0` |

### Tipografi

- Heading: **Figtree** (500/600/700)
- Body: **Noto Sans** (400/500/700) — 15px, line-height 1.6
- Angka & alamat/hash: **JetBrains Mono** 13px, `font-variant-numeric: tabular-nums`

Skala: 13 / 15 / 17 / 20 / 26 / 32 px. Jangan pakai ukuran acak.

### Spacing, radius, elevasi

- Spacing 4/8/12/16/24/32/48 (`p-1 … p-12` Tailwind).
- Radius: kartu 10px, input & tombol 8px, badge 999px.
- Shadow hanya dua: kartu `0 1px 2px rgb(15 23 42 / .06)`, dialog
  `0 8px 24px rgb(15 23 42 / .10)`.
- Lebar konten maksimum **1120px** di tengah; sidebar 248px.

### Ikon

Pakai **Phosphor/heroicon SVG** dari sprite lokal (bukan emoji). Ikon
dekoratif di samping teks: `aria-hidden="true"`. Ikon berdiri sendiri
(tombol copy): `<button aria-label="Salin alamat wallet">`.

---

## 4. Struktur informasi & navigasi

Sidebar tetap, dikelompokkan 3:

```
EHR Traceability
├─ Ringkasan            /                     [dashboard]
├─ Rekam Medis
│   ├─ Daftar Batch     /rekam-medis          [folder_shared]
│   └─ Buat Batch       /rekam-medis/baru     [note_add]
├─ Akun
│   ├─ Wallet & Transaksi /wallet             [wallet]
│   └─ Hak Akses        /hak-akses            [shield]
└─ kartu status: RPC · Chain · Wallet
```

Pemetaan ke permintaan modul:

| Modul | Halaman kita |
|---|---|
| Dashboard | `/` — proyek, status koneksi, ringkasan |
| Data Management | `/rekam-medis` — daftar dari kontrak |
| Form Input | `/rekam-medis/baru` — dengan validasi |
| Detail Data | `/rekam-medis/{token_id}` — detail + aksi |
| Wallet & Transaction | `/wallet` — alamat, jaringan, saldo, status tx |
| *(contoh EHR di modul)* Access Management | `/hak-akses` — fungsional: izin dokter oleh pasien, penunjukan dokter oleh resepsionis |

Status "menunggu konfirmasi / berhasil / gagal" ditampilkan di komponen
**tx panel** yang sama di semua halaman yang mengirim transaksi.

---

## 5. Spesifikasi halaman

### 5.1 Ringkasan — `/`

**Tujuan:** dalam 5 detik user tahu: jaringan hidup? wallet nyambung?
kontrak benar? ada berapa data?

```
┌ Rekam Medis Pasien                              [● Localhost 31337] ┐
│ Pantau rekam medis on-chain dan status jaringan                    │
├────────────┬────────────┬────────────┬────────────┬────────────────┤
│ Jaringan   │ Wallet     │ Kontrak    │            │                │
│ ● Tersambung│ 0x7099…79C8│ 0x5FbD…aa3 │            │                │
│ blok #42   │ 9999.99 ETH│ EHR · ERC721│           │                │
├────────────┴────────────┴────────────┴────────────┴────────────────┤
│ [ 12 Total batch ] [ 9 Pasien ] [ 3 Selesai ] [ 9 Dalam proses ]  │
├──────────────────────────────────┬─────────────────────────────────┤
│ Distribusi status                │ Batch terbaru                   │
│ CREATED    ████████████ 4        │ #12 P-001 Budi   [CREATED]  →   │
│ EXAMINED   █████████ 3           │ #11 P-014 Sari   [TREATED]  →   │
│ DIAGNOSED  ██████ 2              │ #10 P-009 Agus   [COMPLETED] →  │
│ TREATED    ███ 1                 │                                 │
│ COMPLETED  ███████ 2             │                                 │
└──────────────────────────────────┴─────────────────────────────────┘
```

**Data:** `/api/health` (RPC, chain id, blok, kode kontrak ada/tidak),
`name()`, `symbol()`, `totalSupply()`, lalu `getBatch()` per token untuk
status & nama pasien. Semua di-cache 15 detik (`functools.lru_cache` + TTL
sederhana) supaya tidak hammer RPC saat refresh.

**State:**
- RPC mati → banner kuning "Hardhat RPC tidak dapat diakses" + perintah
  `npx hardhat node`; kartu metrik jadi `—`, bukan `0`.
- Kontrak kosong di alamat itu → banner merah "Tidak ada kontrak di alamat
  ini" + saran deploy ulang.
- Belum ada batch → empty state dengan CTA "Buat batch pertama".

**Aksi:** klik baris "Batch terbaru" → detail. Tombol "Muat ulang data"
manual (tanpa auto-poll, hemat CPU).

---

### 5.2 Daftar Batch — `/rekam-medis`

**Tujuan:** Data Management. Menampilkan data kontrak dalam bentuk daftar
*kartu* (default) atau *tabel* (toggle), bisa dicari & difilter.

```
┌ Daftar Batch Rekam Medis                           12 batch        ┐
│ [Cari nama / ID pasien…]        [Semua ▾] [Milik saya]  [▤|☰]     │
├───────────────────────────────────────────────────────────────────┤
│ #12  Budi Santoso          P-001           [ CREATED ]    12 Nov   │
│      Keluhan: demam 3 hari         [●○○○○] 1/5        Detail →    │
├───────────────────────────────────────────────────────────────────┤
│ #11  Sari Dewi             P-014           [ TREATED ]    11 Nov   │
│      Keluhan: nyeri dada           [●●●●○] 4/5        Detail →    │
└───────────────────────────────────────────────────────────────────┘
```

**Filter:** kata kunci (nama/ID pasien/token id), status (semua + 5 status),
"Milik saya" (pasien: batch yang NFT-nya dia pegang; dokter: batch yang
ditugaskan kepadanya), dan dokter penanggung jawab. Filter dikerjakan di
server via query string (`?q=&status=&mine=1&doctor=…&view=table`) supaya
URL bisa di-share — bukan filter JS yang hilang saat refresh.

**Tampilan tabel** (untuk modul yang minta tabel): kolom Token ID · ID
Pasien · Nama · Status · Dokter (short) · Pemilik (short) · Dibuat · aksi
"Detail". Di layar < 768px, tabel di-scroll horizontal di dalam wrapper,
halaman tidak melebar.

**State:** empty (belum ada data), empty karena filter ("Tidak ada batch
cocok filter" + tombol reset), error RPC.

**Catatan data:** daftar berasal dari `totalSupply()` + `getBatch()`, jadi
tidak bergantung pada event log. Kalau node Hardhat di-restart, state chain
memang hilang seluruhnya — empty state perlu menjelaskan itu dan mengarahkan
deploy ulang, bukan menyiratkan bug.

---

### 5.3 Buat Batch — `/rekam-medis/baru`

**Tujuan:** Form Input + validasi + transaksi `createBatch`.

Layout 2 kolom: form (kiri, 2/3) + ringkasan sticky (kanan, 1/3).

```
┌ Buat Batch Rekam Medis                                            ┐
├────────────────────────────────────┬──────────────────────────────┤
│ Data pasien                        │ Ringkasan                    │
│ ID Pasien *   [P-001            ]  │ Pasien  Budi Santoso         │
│ Nama Pasien * [Budi Santoso     ]  │ ID      P-001                │
│ Keluhan *     [demam 3 hari     ]  │ Keluhan demam 3 hari         │
│              0/280                 │ Dokter  dr. Sari (0x3C44…)   │
│ Penugasan                          │ Pemilik 0x7099…79C8 (pasien) │
│ Dokter *      [dr. Sari      ▾ ]   │ Biaya   gas lokal (gratis)   │
│ Wallet pasien*[0x7099…         ]   │                              │
│ Metadata URI  [otomatis        ]   │ [ Siapkan transaksi ]        │
│ ℹ ID pasien belum tentu unik di    │ Transaksi dibuat di server,  │
│   kontrak — pastikan manual.       │ ditandatangani MetaMask.     │
└────────────────────────────────────┴──────────────────────────────┘
```

**Khusus peran:** halaman ini hanya bisa dipakai wallet berperan
`RESEPSIONIST`. Peran lain melihat empty-state "Hanya resepsionis yang bisa
mendaftarkan pasien" + tombol kembali (bukan form yang pasti gagal).

**Dropdown dokter** diisi dari `getDoctors()` (registry on-chain), lengkap
dengan alamat pendek. Kalau daftar kosong → empty-state "Belum ada dokter
terdaftar" + petunjuk menghubungi admin (`setRole`).

**Validasi (dicek sebelum transaksi dibuat):**

| Field | Aturan | Pesan |
|---|---|---|
| ID Pasien | wajib, 3–32 char, `^[A-Za-z0-9-]+$` | "ID pasien wajib diisi (3–32 karakter, huruf/angka/strip)." |
| Nama Pasien | wajib, 2–64 char, huruf & spasi | "Nama pasien wajib diisi." |
| Keluhan | wajib, 5–280 char | "Keluhan minimal 5 karakter." |
| Dokter | wajib dipilih dari `getDoctors()` | "Pilih dokter penanggung jawab." |
| Wallet pasien | wajib, `Web3.is_address`, checksum | "Alamat wallet tidak valid." |
| Metadata URI | opsional (lihat catatan) | "Metadata harus diawali ipfs:// atau https://." |

Aturan keras di kontrak hanya "tidak boleh kosong" — validasi di atas lebih
ketat dari kontrak, dan itu disengaja (biar UI-nya kelihatan serius).
Tampilkan **ringkasan error di atas form** ("Ada 3 masalah pada form") +
pesan inline di tiap field + fokus ke ringkasan error pertama.

**Metadata URI:** default **otomatis** — server membuat
`data:application/json;base64,…` berisi `{"name":"EHR Batch #<id>",
"description":"Rekam medis ...","attributes":[{"trait_type":"status",
"value":"CREATED"}]}`. Isinya sengaja **tanpa nama/ID pasien** supaya tidak
menambah PII baru ke chain. Field "lanjutan" bisa dibuka untuk mengisi
`ipfs://…` asli kalau nanti ada upload.

**Alur kirim:** lihat §7. Setelah sukses, tampilkan `tokenId` hasil parse
event `BatchCreated` dan tombol "Lihat detail batch".

---

### 5.4 Detail Batch — `/rekam-medis/{token_id}`

**Tujuan:** Detail Data + aksi tulis. Ini pengganti tab "Update Status" dan
"Tindakan & Obat" yang sekarang harus input token ID manual.

```
┌ ← Daftar Batch                                                     ┐
│ Budi Santoso            P-001      [ CREATED ]      Token #12      │
│ Dibuat 12-11-2026 09:14 · Pemilik 0x7099…79C8 · Soulbound          │
├────────────────────────────────┬──────────────────────────────────┤
│ Progres status                 │ Aksi (tergantung peran wallet)   │
│ 1 CREATED      ● sekarang      │ Kamu: DOKTER dr. Sari            │
│ 2 EXAMINED     ○               │ [ Majukan ke EXAMINED ]          │
│ 3 DIAGNOSED    ○               │ ──────────────────────────────   │
│ 4 TREATED      ○               │ Isi tindakan & obat              │
│ 5 COMPLETED    ○               │ [ Tindakan… ] [ Obat… ]          │
│                                │ [ Simpan tindakan ]              │
├────────────────────────────────┴──────────────────────────────────┤
│ Data medis        │ NFT & penugasan                             │
│ Keluhan  demam 3 h│ Dokter  0x3C44…93BC  ● Izin aktif  [cabut]  │
│ Tindakan —        │ Token   #12 · ERC-721 · soulbound           │
│ Obat     —        │ Pemilik 0x7099…79C8 [salin]                 │
│                   │ Metadata data:application/json… [salin]     │
├───────────────────┴───────────────────────────────────────────────┤
│ Riwayat (terbaru di atas)                                         │
│ ● 12-11 09:20  Status diperbarui    0x3C44…93BC  (dokter)         │
│ ● 12-11 09:18  Izin dokter diberikan 0x7099…79C8  (pasien)         │
│ ● 12-11 09:14  Batch dibuat         0x7099…79C8  (resepsionis)     │
└───────────────────────────────────────────────────────────────────┘
```

**Aturan aksi per peran (mengikuti kontrak, tanpa janji palsu):**

| Peran wallet | Yang tampil |
|---|---|
| **Dokter** (ditugaskan) + izin aktif | tombol "Majukan ke <status berikut>" + form tindakan & obat |
| **Dokter** (ditugaskan) + izin **belum** ada | aksi disabled + caption "Menunggu izin pasien. Minta pasien membuka halaman ini dan menekan *Izinkan dokter*." |
| **Dokter** (bukan penanggung jawab) | read-only + caption "Batch ini ditangani dokter lain." |
| **Pasien** (pemilik NFT) | tombol "Izinkan dokter" / "Cabut izin"; read-only untuk data klinis |
| **Resepsionis** | dropdown "Ganti dokter penanggung jawab" (dari `getDoctors()`) |
| **Admin / tanpa peran** | read-only + banner peran (`getRole`) |

Aturan tambahan:
- Status `COMPLETED` → semua aksi tulis hilang, ganti panel "Rekam medis
  selesai dan tidak dapat diubah."
- Tombol majukan hanya ke **satu tahap berikutnya** (kontrak menolak
  lompatan) — jadi tidak ada dropdown status.
- Riwayat dari `getHistory()` sudah terbalik (terbaru dulu), jangan dibalik
  lagi. Label aksi baru: `DOCTOR_ASSIGNED`, `CONSENT_GRANTED`,
  `CONSENT_REVOKED`.
- Ganti dokter otomatis mencabut izin dokter lama — UI harus memberi tahu
  sebelum konfirmasi ("Izin dokter sebelumnya akan dicabut dan pasien perlu
  menyetujui dokter baru").

**State:** token tidak ada → halaman 404 custom ("Batch tidak ditemukan")
dengan CTA kembali ke daftar, bukan stack trace. Wallet belum konek →
data tetap terbaca, aksi disabled + CTA "Hubungkan wallet".

---

### 5.5 Wallet & Transaksi — `/wallet`

**Tujuan:** Modul minta alamat wallet + status transaksi.

```
┌ Wallet & Transaksi                                                │
├───────────────────────────────┬───────────────────────────────────┤
│ Alamat     0x7099…79C8 [salin]│ Transaksi sesi ini                │
│ Jaringan   Hardhat Local 31337│ ✓ Buat batch Budi    blok 42  →   │
│ Saldo     9999.99 ETH         │ ⏳ Majukan #11      menunggu…     │
│ Status     ● Terhubung        │ ✕ Isi obat #12      reverted      │
│ [ Ganti akun ] [ Putuskan ]   │                                   │
├───────────────────────────────┴───────────────────────────────────┤
│ Informasi teknis                                                  │
│ RPC http://127.0.0.1:8545 · Chain 31337 · Blok #42 · Gas 21000    │
└───────────────────────────────────────────────────────────────────┘
```

**Isi:** alamat (mono, tombol salin), chain id + kecocokan dengan RPC,
saldo ETH (dibaca Web3.py), tombol ganti/putus wallet, riwayat transaksi
sesi ini (disimpan di `localStorage`, bisa dihapus), dan info teknis RPC.

**State penting:**
- Wallet belum ada → kartu CTA "Hubungkan MetaMask" + link pasang ekstensi.
- Chain MetaMask ≠ RPC → banner kuning "Jaringan MetaMask berbeda" + tombol
  "Tambah/Switch ke Hardhat Local" (pakai `wallet_addEthereumChain`).
- RPC mati → saldo `—`, banner.

### 5.6 Hak Akses — `/hak-akses`

**Tujuan:** tempat pasien memberi/mencabut izin dokter dan resepsionis
menunjuk dokter — plus penjelasan transparan siapa boleh menulis apa.

```
┌ Hak Akses                                                        │
│ Hak tulis = peran + penugasan + izin pasien (bukan pemilik NFT).  │
├───────────────────────────────────────────────────────────────────┤
│ Peran wallet kamu: PASIEN                                          │
├──────────────┬───────────────────┬──────────────┬────────────────┤
│ Batch        │ Dokter            │ Izin         │ Aksi           │
│ #12 Budi     │ 0x3C44…93BC       │ ● aktif      │ [Cabut izin]   │
│ #11 Sari     │ 0x90F7…b906       │ ○ belum ada  │ [Izinkan]      │
└──────────────┴───────────────────┴──────────────┴────────────────┘
│ Dokter terdaftar: 0x3C44… (dr. Sari), 0x90F7… (dr. Agus)          │
│ Resepsionis bisa mengganti dokter dari halaman detail batch.      │
└───────────────────────────────────────────────────────────────────┘
```

**Aksi per peran:**

| Peran | Isi halaman |
|---|---|
| Pasien | daftar batch miliknya + tombol **Izinkan / Cabut izin** (hanya batch dengan status belum `COMPLETED`) |
| Resepsionis | tabel semua batch + dokter penanggung jawab + consent aktif, tautan ke detail untuk ganti dokter |
| Dokter | daftar batch yang ditugaskan kepadanya + status izin (menunggu / aktif) |
| Admin | daftar dokter terdaftar (`getDoctors()`) + peran tiap akun |

Penjelasan yang ditampilkan (bukan hiasan, ini jawaban untuk dosen):
`updateStatus()` dan `updateTreatment()` memerlukan tiga syarat sekaligus —
peran `DOCTOR`, penugasan dokter pada batch, dan `consent[tokenId][doctor]`.

**Batas jujur:** `consent` mengatur izin **menulis**, bukan kerahasiaan baca.
Data medis tersimpan plaintext di chain lokal, jadi siapa pun yang membaca
chain tetap bisa melihatnya.

---

## 6. Komponen bersama

| Komponen | Isi | Catatan aksesibilitas |
|---|---|---|
| `status_badge` | label status + warna | teks selalu ada, warna bukan satu-satunya penanda |
| `stepper` | 5 tahap bernomor, tahap aktif ditandai teks "sekarang" | jangan hanya warna |
| `metric_card` | label, nilai, ikon, hint | nilai `—` saat data tak tersedia |
| `empty_state` | ikon, judul, 1 kalimat, CTA | CTA konkret, bukan "coba lagi" doang |
| `tx_panel` | state mesin transaksi (§7) | `role="status"` + `aria-live="polite"` |
| `copy_button` | salin alamat/hash | `aria-label`, feedback "Tersalin" 2 detik |
| `confirm_dialog` | ringkasan sebelum kirim | fokus masuk ke dialog, Esc menutup, fokus balik |
| `filter_pills` | filter status | `<a>` dengan URL asli, bukan JS-only |
| `data_table` | tabel + wrapper scroll | `<caption>` + urutan kolom stabil |
| `role_chip` | peran wallet saat ini | resolusi: `getRole` != NONE → peran itu; NONE tapi memiliki NFT → **PASIEN**; selain itu "tanpa peran" |

---

## 7. Alur transaksi (state machine)

Berlaku untuk `createBatch`, `updateStatus`, `updateTreatment`.

```
IDLE
 └─ submit form/aksi
    └─ VALIDATING        (server: cek field, alamat, tipe data)
       ├─ gagal → INVALID      → ringkasan error + inline, tetap di form
       └─ lolos → SIMULATING   (server: .call({from: wallet}) = dry-run)
          ├─ revert → REVERTED → tampilkan alasan asli kontrak
          └─ ok → READY        → dialog konfirmasi berisi ringkasan
             └─ klik "Buka MetaMask" → SIGNING
                ├─ user tolak → REJECTED   → "Transaksi dibatalkan di MetaMask."
                └─ hash didapat → PENDING  → panel: hash, "Menunggu konfirmasi…"
                   └─ poll /api/tx/{hash} tiap 2 dtk (maks 60 dtk)
                      ├─ status 1 → SUCCESS  → toast + blok, gas, (tokenId baru)
                      ├─ status 0 → FAILED   → "Transaksi gagal (reverted)."
                      └─ > 60 dtk → TIMEOUT  → "Belum dikonfirmasi. Cek lagi."
```

Teks status (persis seperti yang diminta modul):

| State | Teks UI |
|---|---|
| PENDING | "Menunggu konfirmasi… (hash 0xab…)" |
| SUCCESS | "Transaksi berhasil · blok 42 · gas 84.512" |
| FAILED | "Transaksi gagal: <alasan revert>" |
| REJECTED | "Kamu membatalkan transaksi di MetaMask." |

Alasan revert kontrak sudah berbahasa Indonesia (`"Pasien belum memberi izin"`,
`"Bukan dokter penanggung jawab"`, `"Status tidak valid"`,
`"Batch tidak ditemukan"`) — tampilkan apa adanya, jangan diganti pesan
generik. Pesan-pesan ini juga jadi petunjuk langkah berikutnya, jadi jangan
diperhalus jadi "Transaksi gagal".

**Kenapa dry-run dulu:** supaya user tidak membuang waktu tanda tangan
transaksi yang pasti ditolak (misal belum ada consent). Pola ini sudah ada di
`app.py` lama dan layak dipertahankan.

---

## 8. Pemetaan UI ↔ smart contract

| Elemen UI | Endpoint | Fungsi kontrak |
|---|---|---|
| Chip jaringan & blok | `GET /api/health` | `w3.is_connected`, `eth.chain_id`, `eth.block_number` |
| Kartu kontrak | dashboard | `name()`, `symbol()`, `get_code()` |
| Daftar & filter batch | `GET /rekam-medis` | `totalSupply()` + `getBatch()` |
| Kartu detail | `GET /rekam-medis/{id}` | `getBatch()`, `ownerOf()`, `tokenURI()` |
| Riwayat | detail | `getHistory()` |
| Peran wallet | semua halaman | `getRole(address)` |
| Dropdown dokter | form & detail | `getDoctors()` |
| Form buat batch | `POST /api/tx/build {action:"createBatch"}` | `createBatch(...)` (simulasi `.call`, kirim via MetaMask) |
| Majukan status | `POST /api/tx/build {action:"updateStatus"}` | `updateStatus()` |
| Simpan tindakan | `POST /api/tx/build {action:"updateTreatment"}` | `updateTreatment()` |
| Izinkan / cabut dokter | `POST /api/tx/build {action:"setConsent"}` | `setConsent()` |
| Ganti dokter | `POST /api/tx/build {action:"assignDoctor"}` | `assignDoctor()` |
| Status transaksi | `GET /api/tx/{hash}` | `eth.wait_for_transaction_receipt` |
| Token ID baru | respons tx | event `BatchCreated` di receipt |
| Saldo & consent | wallet, hak akses | `eth.get_balance`, `consent(tokenId, doctor)` |

API kontrak internal:

```http
POST /api/tx/build
{ "action": "createBatch", "from": "0x7099…", "args": { ... } }
→ 200 { "to": "0x5FbD…", "data": "0x…", "label": "Buat batch Budi", "id": "…" }
→ 400 { "error": "Pasien belum memberi izin" }

GET /api/tx/{hash}
→ { "state": "pending|success|failed", "block": 42, "gas": 84512, "tokenId": 12, "reason": "…" }

GET /api/health
→ { "rpc": true, "chainId": 31337, "block": 42, "contract": true }
```

Prinsip: **server tidak pernah memegang private key**. Server hanya
menyiapkan `to` + `data`; tanda tangan di MetaMask.

---

## 9. Catatan implementasi

- **Tanpa build step di sisi user**: Tailwind Play CDN **tidak** dipakai.
  CSS dibangun sekali dengan Tailwind CLI standalone (`tailwindcss -c
  web/tailwind.config.js -i web/static/css/input.css -o
  web/static/css/app.css --minify`) dan hasilnya di-commit. Efeknya: satu
  request CSS 16 KB, tanpa kompilasi di browser — jauh lebih ringan untuk
  laptop 4 GB. Binary CLI tidak ikut repo (bisa diunduh ulang).
- **Token warna** ditaruh sebagai CSS variables di `app.css`, Tailwind
  `theme.extend.colors` memetakan ke `var(--…)` — jadi dark mode cuma
  ganti blok `[data-theme="dark"]`, bukan dua set class.
- **Cache**: `lru_cache` TTL ~15 detik untuk health + daftar batch. Laptop
  low-spec: hindari auto-refresh, sediakan tombol "Muat ulang".
- **ABI & alamat** dibaca dari `artifacts/…/EHRTraceability.json` dan
  `deployment.json` (sama seperti `app.py` sekarang). Tidak ada duplikasi
  ABI manual.
- **Checksum address** wajib (`Web3.to_checksum_address`) sebelum dipakai
  di `call`/`encode_abi`, kalau tidak web3.py 8 melempar error.
- **`app.py` lama** jangan dihapus dulu; biarkan sebagai pembanding sampai
  versi baru jalan. Catatan: setelah kontrak baru di-deploy, `app.py` lama
  **tidak kompatibel** (signature `createBatch` berubah) — jangan dipakai
  untuk demo.
- **`contracts/`** hanya berubah lewat rancangan di
  `docs/Rancangan Smart Contract - Peran & Consent.md`. `Lock.sol` dan
  `hardhat.config.js` tidak disentuh.

---

## 10. Responsif & aksesibilitas

Cek sebelum bilang selesai:

- [ ] 375 px: sidebar jadi top-bar/drawer, kartu 1 kolom, tabel scroll
      horizontal di wrapper (halaman tidak melebar).
- [ ] 768 / 1024 / 1440 px: grid 2–4 kolom, konten tetap maks 1120 px.
- [ ] Kontras teks ≥ 4,5:1 di light **dan** dark (jangan asumsi light aman).
- [ ] Focus ring terlihat (`outline` 2px `--primary`, offset 2px) untuk
      semua elemen interaktif; urutan tab = urutan visual.
- [ ] Status transaksi diumumkan (`aria-live="polite"`), error form
      diumumkan (`role="alert"`) dan fokus pindah ke ringkasan error.
- [ ] `prefers-reduced-motion` → matikan transisi non-esensial.
- [ ] Semua field punya `<label>` (bukan placeholder saja).
- [ ] Tombol ikon punya `aria-label`; ikon dekoratif `aria-hidden`.
- [ ] Tidak ada emoji sebagai ikon struktural.
- [ ] Status peran (Dokter/Resepsionis/Pasien/Tanpa peran) selalu ditulis
      sebagai teks, bukan hanya warna badge.

---

## 11. Rencana kerja (belum dieksekusi)

| Fase | Isi | Hasil yang bisa dicek |
|---|---|---|
| **0a** ✅ | Kontrak peran & consent + test | `npx hardhat test` 29 lulus |
| **0b** ✅ | Seed peran di `deploy.js`, deploy + `seed-demo.js` | 4 batch demo, 4 akun berperan benar |
| **1** ✅ | Scaffold FastAPI, `chain.py`, base layout, token, `/api/health` | dashboard menampilkan chain 31337, kontrak, `totalSupply`, dokter; RPC mati → banner |
| **2** ✅ | Dashboard + Daftar Batch (read-only) | data asli dari kontrak tampil, filter jalan |
| 3 ✅ | Form Buat Batch + `tx.py` + MetaMask + tx panel | satu transaksi `createBatch` sukses dari UI |
| 4 | Detail + majukan status + tindakan + consent | alur 3 peran jalan dari UI |

Catatan fase 2: halaman detail `/rekam-medis/{token_id}` ikut dibuat dalam
versi **read-only** (stepper, data medis, NFT & penugasan, riwayat) supaya
tautan dari daftar tidak 404. Tombol aksi tulis tetap milik fase 4.
Filter disimpan di query string (`q`, `status`, `doctor`, `mine`, `wallet`,
`view`) supaya URL bisa dibagikan dan tahan refresh.

Catatan fase 3:
- Modul baru: `web/validate.py` (aturan form, satu sumber kebenaran — JS
  tidak menduplikasi regex) dan `web/tx.py` (validasi → dry-run `.call({from})`
  → calldata; plus pembacaan receipt + parsing event `BatchCreated`).
- Endpoint: `POST /api/tx/build`, `GET /api/tx/{hash}`, `GET /api/role`.
  Error validasi balik sebagai `400 {error, fields}` supaya pesan inline
  berasal dari server, bukan dari dua tempat.
- Gerbang peran: halaman membaca `getRole(alamat)` dan hanya menampilkan form
  untuk `RESEPSIONIST`; peran lain dapat empty-state penjelas. Kalau wallet
  belum konek atau MetaMask tidak ada, alasannya ditulis eksplisit.
- Metadata NFT default `data:application/json;base64,…` tanpa nama/ID pasien
  (jangan menambah PII baru ke chain).
- `chain.refresh()` sekarang juga membaca ulang `deployment.json` (cek mtime),
  karena deploy ulang mengubah alamat kontrak — sebelumnya UI diam-diam
  membaca kontrak lama.
- Uji alur penuh di headless Chromium memakai **provider wallet tiruan** yang
  meneruskan `eth_sendTransaction` ke node lokal (Chromium headless tidak
  punya MetaMask): validasi kosong → 5 error, dialog konfirmasi, sukses
  blok 48 gas 641.508 token #5, penolakan MetaMask (`4001`) → pesan
  "Kamu membatalkan transaksi di MetaMask.", admin → empty-state peran.
| 5 | Wallet + Hak Akses + responsif + README | semua halaman modul lengkap |

Aturan: satu fase selesai & dites, baru lanjut. Jangan bangun semua
sekaligus lalu debug di akhir.

---

## 12. Screenshot & skrip video (kamu yang rekam)

Modul minta **minimal 4 screenshot** dan **video 3–5 menit**. Ambil 7
screenshot ini (1080p, browser zoom 100%, mode light):

1. Dashboard penuh (status jaringan + metrik + distribusi).
2. Daftar Batch dengan filter aktif.
3. Form Buat Batch **dalam keadaan error validasi** (biar kelihatan
   validasinya jalan).
4. Detail Batch (stepper + data medis + riwayat).
5. Tx panel sukses (blok, gas, token ID baru).
6. Halaman Wallet (alamat + peran + riwayat transaksi).
7. Halaman Hak Akses (izin dokter aktif/belum).

**Skrip video (±4 menit) — 3 peran, 3 akun:**

| Waktu | Isi |
|---|---|
| 0:00–0:20 | Judul, nama kelompok, masalah: "rekam medis terpusat rawan diubah; di sini tiap batch jadi NFT soulbound dan tiap tulisan terikat peran." |
| 0:20–0:45 | Dashboard: RPC tersambung, chain 31337, kontrak `EHRTraceability`, angka batch, dan peran wallet aktif. |
| 0:45–1:05 | Daftar Batch: cari, filter status, toggle tabel. |
| 1:05–1:50 | **Resepsionis** membuat batch: submit kosong → error validasi; isi benar + pilih dokter → MetaMask → sukses + token ID. |
| 1:50–2:20 | **Pasien** membuka Hak Akses → "Izinkan dokter" → tunjukkan riwayat `CONSENT_GRANTED`. |
| 2:20–2:55 | **Dokter** membuka detail → majukan status ke EXAMINED → isi tindakan & obat → sukses. |
| 2:55–3:20 | Tunjukkan pembatasan: resepsionis coba majukan status → ditolak "Bukan dokter"; atau pasien coba isi obat → tidak ada tombolnya. |
| 3:20–3:45 | Wallet: alamat, saldo, hash; jelaskan private key tidak pernah masuk server. |
| 3:45–4:10 | Tutup: arsitektur singkat (Jinja/FastAPI → Web3.py → Hardhat) + mengapa consent penting. |

Tips rekam: siapkan 3 akun Hardhat di MetaMask **sebelum** mulai, jangan
tampilkan seed phrase, dan buat 2–3 batch contoh supaya daftar tidak kosong.

---

## 13. Checklist deliverable modul

- [ ] Kode aplikasi + link GitHub.
- [ ] Screenshot ≥ 4 halaman (§12).
- [ ] README: cara install, `npx hardhat node`, deploy, jalankan Uvicorn,
      buka `127.0.0.1:8000`, sambungkan MetaMask ke Hardhat Local.
- [ ] Video 3–5 menit.
- [ ] Penjelasan tiap halaman + hubungan UI ↔ kontrak (tabel §8 bisa
      langsung dipakai).

---

## 14. Keputusan yang sudah final

1. **Stack**: FastAPI + Jinja2 + Tailwind + Alpine + ethers.js, tanpa Node.
   Backend tetap memakai Web3.py sesuai syarat modul.
2. **Judul**: "EHR Traceability" (sama dengan `name()` kontrak), subtitle
   "Rekam Medis Pasien Terdesentralisasi". Identitas kelompok di footer.
3. **Palet**: clinical cyan `#0891B2` + hijau `#047857`. Warna identitas
   kelompok (kalau ada) hanya aksen tipis di logo, bukan mewarnai seluruh UI.
4. **Metadata URI**: dibuat **otomatis** sebagai `data:application/json`
   tanpa PII tambahan; field override `ipfs://` dibuka kalau perlu.
5. **Hak Akses fungsional**: kontrak diubah sesuai
   `docs/Rancangan Smart Contract - Peran & Consent.md` (peran + penugasan
   dokter + consent pasien + soulbound).
6. **Tema**: light default, dark disiapkan tapi bukan prioritas.
7. **Bahasa UI**: Indonesia, istilah teknis tetap Inggris (wallet, batch,
   gas, token ID).

**Satu hal yang belum diputuskan** (tidak menghalangi implementasi UI):
apakah pasien perlu tombol terpisah "Tandatangani rekam medis diterima"
selain consent. Rekomendasi: **belum**, karena consent sudah mewakili
"menyetujui"; tambah nanti kalau dosen meminta.
