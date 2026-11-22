# Rekam Medis Pasien (EHR) Berbasis Blockchain

Aplikasi pencatatan dan pengelolaan rekam medis pasien yang menggunakan **blockchain** untuk menjaga integritas data dan jejak akses (audit trail).

## Deskripsi

Aplikasi ini membantu fasilitas kesehatan dan tenaga medis mencatat, melihat, dan mengelola rekam medis pasien secara aman. Setiap perubahan dan akses terhadap data dicatat melalui blockchain sehingga data sulit dimanipulasi dan semua aktivitas dapat ditelusuri.

## Fitur Utama

- Pencatatan rekam medis pasien oleh tenaga medis
- Integritas data terjaga melalui blockchain
- Jejak akses data (siapa mengakses, kapan, dan apa)
- Pengaturan izin akses untuk dokter atau fasilitas kesehatan
- Ringkasan statistik pasien dan aktivitas akses

## Konsep Halaman (UI)

| No | Halaman | Deskripsi |
|----|---------|-----------|
| 1 | **Dashboard** | Menampilkan jumlah pasien, jumlah rekam medis, dan aktivitas akses |
| 2 | **Patient List** | Daftar pasien berdasarkan ID |
| 3 | **Patient Detail** | Profil dasar pasien dan ringkasan informasi |
| 4 | **Medical Record** | Daftar rekam medis, diagnosis, dan tanggal pemeriksaan |
| 5 | **Add Medical Record** | Form pencatatan pemeriksaan oleh tenaga medis |
| 6 | **Access Management** | Pengaturan izin akses dokter atau fasilitas kesehatan |

## Alur Penggunaan

1. Tenaga medis membuka **Dashboard** untuk melihat ringkasan data.
2. Memilih pasien dari **Patient List** berdasarkan ID.
3. Melihat profil di **Patient Detail**, lalu riwayat di **Medical Record**.
4. Menambah catatan pemeriksaan baru melalui **Add Medical Record**.
5. Mengatur siapa saja yang boleh mengakses data pada **Access Management**.

## Teknologi

> Sesuaikan dengan yang kalian pakai.

- Frontend: _(contoh: React / Next.js / Flutter / HTML-CSS-JS)_
- Styling: _(contoh: Tailwind CSS)_
- Blockchain: _(contoh: Ethereum / Hyperledger / Solidity)_

## Instalasi dan Menjalankan

```bash
# Clone repository
git clone https://github.com/bratayudha07/tugas-herdhat
cd tugas-herdhat

# Install dependency
npm install

# Jalankan aplikasi
npm run dev
```

> Sesuaikan perintah di atas dengan teknologi yang digunakan.

## Struktur Folder

```
.
├── src/
│   ├── pages/        # Halaman (Dashboard, Patient List, dll.)
│   ├── components/   # Komponen UI
│   └── assets/       # Gambar dan aset
├── public/
└── README.md
```

## Tampilan Aplikasi

_Tambahkan screenshot setiap halaman di sini._

| Halaman | Screenshot |
|---------|------------|
| Dashboard | `docs/dashboard.png` |
| Patient List | `docs/patient-list.png` |
| Patient Detail | `docs/patient-detail.png` |
| Medical Record | `docs/medical-record.png` |
| Add Medical Record | `docs/add-record.png` |
| Access Management | `docs/access-management.png` |

## Anggota Kelompok

| Nama | NIM | Peran |
|------|-----|-------|
| ... | ... | ... |
| ... | ... | ... |

## Catatan

Proyek ini dibuat untuk keperluan tugas/pembelajaran. Data pasien yang digunakan merupakan data dummy.
