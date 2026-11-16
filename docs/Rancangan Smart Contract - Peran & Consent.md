---
type: design-doc
project: EHR Traceability (Praktikum Blockchain Pertemuan 11–12)
status: diterapkan 2026-11-16 — 29 test lulus, deploy + seed terverifikasi via Web3.py
last_updated: 2026-11-16
---

# Rancangan Smart Contract — Peran & Consent

Dokumen ini rancangan perubahan `contracts/EHRTraceability.sol` yang sudah
kamu setujui arahnya. **Status: sudah diterapkan** (lihat §9a). Draft kode +
test aslinya tetap disimpan sebagai arsip di:

- `docs/rancangan/EHRTraceability.sol.draft`
- `docs/rancangan/ehr.test.js.draft`

Kalau kamu setuju dengan isi dokumen ini, eksekusinya tinggal menyalin draft
ke `contracts/`, menambah seeding peran di `scripts/deploy.js`, lalu
`npx hardhat compile && npx hardhat test`.

**Status eksekusi:** sudah dijalankan. File yang berubah/baru:
`contracts/EHRTraceability.sol`, `test/ehr.test.js`, `scripts/deploy.js`
(seeding peran), `scripts/seed-demo.js` (data demo 4 batch),
`deployment.json` (alamat + akun demo).

---

## 1. Masalah yang diselesaikan

| Sebelum | Masalah | Sesudah |
|---|---|---|
| `updateStatus` / `updateTreatment` cek `ownerOf == msg.sender` | pasien (pemilik NFT) satu-satunya yang bisa menulis diagnosis & obat | hak tulis = peran **DOKTER** + penugasan + **consent** pasien |
| `createBatch` publik | siapa pun bisa mint rekam medis palsu atas nama siapa pun | hanya **RESEPSIONIS** |
| NFT ERC-721 transferable | hak tulis rekam medis bisa ikut pindah tangan | **soulbound**, transfer ditolak |
| tidak ada jejak pembuat | tak bisa dibuktikan siapa yang mendaftarkan | field `createdBy` |
| tidak ada persetujuan pasien | pasien tak punya kendali apa pun | `setConsent` (beri/cabut izin dokter) |
| `updateTreatment` menimpa data | nilai lama hilang dari audit | event `TreatmentUpdated` (lama → baru) |
| tidak bisa enumerasi token/dokter | UI harus baca event log | `totalSupply()` + `getDoctors()` |
| `updateTreatment` tetap jalan walau status `COMPLETED` | rekam medis "final" masih bisa diubah | ditolak (`Rekam medis sudah selesai`) |

Catatan kejujuran yang tetap berlaku: data medis disimpan **plaintext
on-chain**, jadi siapa pun yang membaca chain bisa melihatnya. `consent` di
sini mengatur **siapa yang boleh menulis/mengubah**, bukan kerahasiaan baca.
Jangan diklaim sebagai fitur privasi saat presentasi.

---

## 2. Model peran

```
enum Role { NONE, RECEPTIONIST, DOCTOR, ADMIN }
```

- **ADMIN** = deployer. Hanya mengelola peran, tidak menyentuh data medis.
- **RECEPTIONIST** = operator pendaftaran: membuat batch, menunjuk dokter.
- **DOCTOR** = penanggung jawab klinis: mengisi tindakan/obat, memajukan status.
- **Pasien** bukan role. Identitasnya = **pemilik NFT** (`ownerOf`). Jadi
  pasien tidak perlu didaftarkan dulu oleh admin.

### Matriks izin

| Aksi | Admin | Resepsionis | Dokter ditugaskan + consent | Dokter lain | Pasien (pemilik) |
|---|---|---|---|---|---|
| `setRole` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `createBatch` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `assignDoctor` | ❌ | ✅ | ❌ | ❌ | ❌ |
| `setConsent` | ❌ | ❌ | ❌ | ❌ | ✅ |
| `updateStatus` | ❌ | ❌ | ✅ | ❌ | ❌ |
| `updateTreatment` | ❌ | ❌ | ✅ | ❌ | ❌ |
| baca `getBatch` / `getHistory` | ✅ semua pihak (read publik) |

Tiga pembatasan yang bikin ini aman:
1. Role saja tidak cukup — dokter harus **ditugaskan** ke batch itu.
2. Penugasan saja tidak cukup — pasien harus **memberi consent**.
3. Consent dicabut otomatis saat dokter diganti, dan semua aksi tulis
   diblokir setelah status `COMPLETED`.

---

## 3. Alur 3 aktor

```
1. Admin      setRole(resepsionis, RECEPTIONIST)
              setRole(dokter, DOCTOR)              (sekali saat deploy/setup)

2. Resepsionis createBatch(id, nama, keluhan, walletPasien, walletDokter, uri)
              → NFT mint ke wallet pasien, status CREATED, doctor = dokter

3. Pasien      setConsent(tokenId, true)           → izin dokter penanggung jawab

4. Dokter      updateTreatment(tokenId, "…", "…")
              updateStatus(tokenId, EXAMINED)      → … → COMPLETED

5. Pasien      setConsent(tokenId, false)          → dokter langsung terblokir
```

Semua langkah 2–5 adalah transaksi dari akun berbeda — ini justru bagus untuk
demo video: tiga peran, tiga akun MetaMask, tiga tanda tangan.

Revert yang bakal muncul kalau alurnya dilanggar (dipakai apa adanya di UI):

| Skenario | Pesan |
|---|---|
| pasien/umum coba buat batch | `Hanya resepsionis` |
| dokter menulis sebelum consent | `Pasien belum memberi izin` |
| dokter lain (bukan penanggung jawab) | `Bukan dokter penanggung jawab` |
| resepsionis menulis data klinis | `Bukan dokter` |
| status dilompati | `Status tidak valid` |
| ubah batch yang sudah selesai | `Rekam medis sudah selesai` |
| transfer NFT | `Rekam medis tidak dapat dipindahkan` |
| alamat dokter tidak terdaftar | `Alamat dokter tidak terdaftar` |

---

## 4. Perubahan skema data

Struct `PatientBatch` — **append-only**, 8 field lama tetap di indeks 0–7
supaya kode pembacaan lama tidak langsung rusak:

```solidity
struct PatientBatch {
    uint256 tokenId;      // 0
    string patientId;     // 1
    string patientName;   // 2
    string complaint;     // 3
    string treatment;     // 4
    string medicine;      // 5
    Status status;        // 6
    uint256 createdAt;    // 7
    address createdBy;    // 8  (resepsionis pembuat)
    address doctor;       // 9  (dokter penanggung jawab)
    address patient;      // 10 (pemilik NFT)
}
```

State baru:

```solidity
mapping(address => Role) public roles;
mapping(uint256 => mapping(address => bool)) public consent;

address[] private doctorList;               // untuk dropdown dokter di UI
mapping(address => uint256) private doctorIndex;  // 1-based, 0 = bukan dokter
```

Enum `Status` **tidak berubah** (5 tahap) — supaya stepper di UI tetap sama.

---

## 5. API kontrak

### Fungsi tulis

| Fungsi | Akses | Perilaku |
|---|---|---|
| `setRole(address, Role)` | ADMIN | set/ubah peran; kelola `doctorList`; tidak bisa mengubah peran diri sendiri |
| `createBatch(patientId, patientName, complaint, patient, doctor, metadataURI)` | RECEPTIONIST | validasi input, mint NFT ke `patient`, simpan `createdBy`/`doctor`, status CREATED |
| `assignDoctor(tokenId, doctor)` | RECEPTIONIST | ganti dokter; **consent dokter lama dicabut**; ditolak kalau sudah COMPLETED |
| `setConsent(tokenId, bool)` | pasien (pemilik NFT) | beri/cabut izin untuk dokter penanggung jawab; ditolak kalau sudah COMPLETED |
| `updateStatus(tokenId, Status)` | dokter ditugaskan + consent | hanya maju **satu** tahap |
| `updateTreatment(tokenId, treatment, medicine)` | dokter ditugaskan + consent | minimal salah satu terisi; ditolak kalau COMPLETED |

### Fungsi baca

| Fungsi | Keterangan |
|---|---|
| `getBatch(tokenId)` | struct lengkap (termasuk 3 field baru) |
| `getHistory(tokenId)` | riwayat, **terbaru dulu** |
| `totalSupply()` | jumlah batch (pengganti `nextTokenId` yang private) |
| `getDoctors()` | daftar alamat dokter terdaftar (sumber dropdown UI) |
| `getRole(address)` / `roles(address)` | peran akun |
| `consent(tokenId, doctor)` | status izin |
| `getOwner` / `getBatchOwner` / `ownerOf` | pemilik NFT |
| `name` / `symbol` / `tokenURI` | metadata ERC-721 |

### Event

| Event | Dipakai untuk |
|---|---|
| `BatchCreated(tokenId, patient, patientName)` | konfirmasi tx + info token ID baru |
| `StatusUpdated(tokenId, old, new)` | jejak perubahan status |
| `TreatmentUpdated(tokenId, oldTreatment, oldMedicine, newTreatment, newMedicine)` | audit nilai lama → baru |
| `DoctorAssigned(tokenId, doctor)` | jejak penugasan |
| `ConsentChanged(tokenId, doctor, granted)` | jejak izin pasien |
| `RoleChanged(account, oldRole, newRole)` | jejak perubahan peran |

UI **tidak perlu** memantau event (sesuai modul). Event hanya untuk audit dan
pembacaan token ID baru dari receipt `createBatch`.

---

## 6. Urutan pengecekan & alasannya

Modifier `onlyDoctorFor(tokenId)` sengaja berurutan begini:

1. `Batch tidak ditemukan` — biar tidak bingung saat token ID salah.
2. `Bukan dokter` — peran dulu.
3. `Bukan dokter penanggung jawab` — baru penugasan.
4. `Pasien belum memberi izin` — terakhir consent.

Urutan ini bikin pesan error di UI selalu menunjuk masalah paling dasar,
tidak melempar "izin belum ada" ke orang yang bahkan bukan dokter.

`setRole` menolak mengubah peran sendiri supaya admin tidak bisa mengunci
dirinya keluar dari kontrak.

---

## 7. Soulbound (NFT tidak bisa dipindah)

```solidity
function _update(address to, uint256 tokenId, address auth)
    internal override returns (address)
{
    address from = _ownerOf(tokenId);
    require(from == address(0), "Rekam medis tidak dapat dipindahkan");
    return super._update(to, tokenId, auth);
}
```

`from == 0` hanya terjadi saat mint. Tidak ada fungsi burn, jadi rekam medis
bertahan permanen. Konsekuensi yang harus disebut saat presentasi: **data
yang salah tidak bisa dihapus**, hanya bisa dimajukan statusnya — karena itu
validasi input di UI jadi penting.

---

## 8. Deployment: seeding peran

`scripts/deploy.js` perlu menambahkan pemberian peran setelah deploy:

```js
const signers = await hre.ethers.getSigners();
const [admin, receptionist, doctor, doctor2, patient] = signers;

await contract.setRole(receptionist.address, 1); // RECEPTIONIST
await contract.setRole(doctor.address, 2);       // DOCTOR
await contract.setRole(doctor2.address, 2);      // DOCTOR (opsional, untuk uji ganti dokter)
```

`deployment.json` sebaiknya menyimpan hint akun demo supaya README/MetaMask
mudah diikuti:

```json
{
  "contract": "EHRTraceability",
  "address": "0x…",
  "network": "localhost",
  "chainId": 31337,
  "demoAccounts": {
    "admin": "0xf39F…2266",
    "receptionist": "0x7099…79C8",
    "doctor": "0x3C44…93BC",
    "doctor2": "0x90F7…b906",
    "patient": "0x9965…A4dc"
  }
}
```

Catatan: alamat **bukan** trust anchor — UI tetap membaca `getRole()` untuk
menampilkan peran wallet yang sedang terhubung. Hint ini hanya untuk
memudahkan setup MetaMask saat demo.

---

## 9. Verifikasi yang sudah dilakukan

Draft diuji di proyek Hardhat terpisah (`/tmp`, compiler 0.8.28, evm cancun,
optimizer 200 runs) — repo tidak diubah.

- Kompilasi: **0 error, 0 warning**, bytecode ter-deploy 14,8 KB (60% dari
  batas 24 KB).
- Test: **20 lulus**, mencakup:
  - deployer otomatis ADMIN; hanya admin bisa memberi peran
  - pasien/stranger ditolak saat `createBatch`
  - NFT mint ke pasien; `createdBy`/`doctor`/`patient` benar
  - dokter ditolak sebelum consent (status & treatment)
  - hanya pemilik NFT yang bisa `setConsent`
  - setelah consent: status & treatment berjalan
  - resepsionis ditolak menulis data klinis
  - dokter lain ditolak walau terdaftar
  - status tidak boleh lompat/mundur
  - transfer & `safeTransferFrom` ditolak (soulbound)
  - ganti dokter mencabut consent lama; dokter baru butuh consent baru
  - pasien cabut izin → dokter langsung terblokir
  - treatment kosong ditolak; riwayat terbaru di atas
  - batch `COMPLETED` tidak bisa diubah lagi (status & treatment)
  - `getDoctors()` menambah/mencabut dokter dengan benar
  - pesan "Batch tidak ditemukan" konsisten

Dua bug ketemu justru karena tes ini ditulis sekarang: `updateTreatment`
masih bisa menulis ke batch `COMPLETED`, dan `consent` dokter lama tidak
dicabut saat dokter diganti. Keduanya sudah diperbaiki di draft.

---

## 9a. Hasil eksekusi (2026-11-16)

1. `contracts/EHRTraceability.sol` diganti dengan draft yang sudah diuji.
2. `test/ehr.test.js` terpasang → `npx hardhat test` = **29 lulus**
   (20 test EHR + 9 test Lock bawaan).
3. `scripts/deploy.js` memberi peran otomatis + menulis `demoAccounts`.
4. `scripts/seed-demo.js` mengisi 4 batch contoh dengan tahap berbeda.
5. Deploy + seed diuji di `npx hardhat node`, lalu dibaca ulang lewat
   **Web3.py** (jalur yang nanti dipakai aplikasi web):

```
rpc: True | chain: 31337 | totalSupply: 4
dokter terdaftar: 0x3C44…93BC, 0x90F7…b906
admin        -> ADMIN
receptionist -> RESEPSIONIS
doctor       -> DOKTER
doctor2      -> DOKTER
patient      -> NONE        ← wajar, pasien bukan role

#1 Budi Santoso  P-001  COMPLETED  consent=ya     riwayat=7
#2 Sari Dewi     P-014  TREATED    consent=ya     riwayat=6
#3 Agus Prakoso  P-009  EXAMINED   consent=ya     riwayat=4
#4 Rina Marlina  P-021  CREATED    consent=belum  riwayat=1
```

**Temuan penting untuk UI:** akun pasien berperan `NONE` karena pasien bukan
role. Jadi identitas harus disimpulkan: `getRole != NONE` → pakai peran itu;
kalau `NONE` tapi `ownerOf` batch tertentu == wallet → tampilkan **PASIEN**;
selain itu baru "tanpa peran". Jangan pakai `getRole` saja untuk menyimpulkan
"akun tidak terdaftar".

Node Hardhat **dimatikan** setelah verifikasi (state hilang). Untuk demo,
jalankan ulang: `npx hardhat node` → `deploy.js` → `seed-demo.js`.

---

## 10. Dampak ke rancangan UI

| Halaman | Yang berubah |
|---|---|
| `/` Dashboard | hitung batch pakai `totalSupply()` (bukan event logs) — lebih cepat & tahan restart node; tambah kartu "Batch menunggu izin" |
| `/rekam-medis` | kolom/tag **Dokter**; filter "milik saya" untuk pasien tetap; dokter bisa filter "ditugaskan ke saya" |
| `/rekam-medis/baru` | field baru **Dokter penanggung jawab** = dropdown dari `getDoctors()`; tombol submit hanya muncul untuk RESEPSIONIST, peran lain dapat empty-state "Hanya resepsionis yang bisa mendaftarkan pasien" |
| `/rekam-medis/{id}` | aksi berubah per peran: dokter → majukan status + isi tindakan; pasien → tombol **Izinkan / Cabut izin dokter**; resepsionis → **Ganti dokter**. Tampilkan status consent |
| `/wallet` | tampilkan **peran wallet** (`getRole`) di samping alamat |
| `/hak-akses` | dari halaman baca jadi fungsional: daftar dokter terdaftar, siapa penanggung jawab tiap batch, consent aktif/tidak, aksi sesuai peran |
| Semua | identitas wallet: `getRole` != NONE → pakai peran itu; NONE tapi memiliki NFT → **PASIEN**; selain itu baru banner "Akun ini tidak punya peran." |

**`app.py` lama akan rusak** setelah kontrak baru di-deploy (signature
`createBatch` berubah, field struct bertambah). Itu wajar karena kita memang
menggantinya dengan web app. Jangan dijalankan lagi setelah redeploy, dan
jangan dihapus sebelum versi baru terbukti jalan.

---

## 11. Yang sengaja belum dikerjakan

| Fitur | Kenapa ditunda | Kalau mau ditambah nanti |
|---|---|---|
| `voidBatch` / amendemen rekam medis | menambah status & alur UI; belum perlu untuk tugas UI | ~15 baris + 1 status/flag |
| Tanda tangan "rekam medis diterima" oleh pasien | consent sudah cukup mewakili "menyetujui" | ~10 baris + 1 tombol |
| Enkripsi data medis / simpan di IPFS | mengubah narasi tugas jadi kriptografi; butuh kunci pasien | fase lanjutan |
| ACL per-field (dokter A hanya lihat diagnosis) | kompleks & tidak ada di kontrak saat ini | redesain besar |
| Enumerasi batch per pasien / per dokter | UI sudah bisa filter dari `totalSupply` (volume demo kecil) | tambah `mapping(address => uint256[])` |
| Event monitoring / histori realtime | modul bilang tidak perlu | — |

---

## 12. Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Narasi UTS berubah ("pasien pemilik & penulis") | jelaskan sebagai perbaikan pasca-evaluasi: pasien tidak etis menulis diagnosisnya sendiri |
| Lupa redeploy → UI baca ABI lama | `deployment.json` + cek kode kontrak di `/api/health`; UI menolak jalan kalau ABI/alamat tidak cocok |
| Demo butuh 4 akun MetaMask | seed 3 peran di deploy + panduan impor akun di README; sediakan halaman Hak Akses untuk memverifikasi peran |
| Consent bikin alur demo lebih panjang | justru jadi bahan video: 3 tanda tangan berbeda = bukti pembatasan akses bekerja |
| Data uji lama hilang setelah redeploy | data lama memang hanya lokal; siapkan 2–3 batch contoh sebelum rekam video |

---

## 13. Checklist eksekusi — selesai

- [x] `contracts/EHRTraceability.sol` diganti draft teruji
- [x] `test/ehr.test.js` terpasang
- [x] `scripts/deploy.js` seeding peran + `demoAccounts`
- [x] `scripts/seed-demo.js` data demo
- [x] `npx hardhat compile && npx hardhat test` → 29 lulus
- [x] `npx hardhat node` + deploy + seed + verifikasi Web3.py
- [ ] Fase UI (scaffold FastAPI) — sesuai rancangan UI §11

---

## 14. Default yang dipakai (tidak perlu dijawab)

1. **Jumlah dokter seed**: 2 (satu untuk demo normal, satu untuk mendemokan
   ganti dokter).
2. **Pasien demo**: akun Hardhat #4–#7 untuk empat batch contoh.
3. **Akun #1 (`0x7099…79C8`)**: RESEPSIONIS — akun yang biasanya aktif di
   MetaMask saat demo dimulai.

Semua bisa diubah di blok `SIGNERS` / `SCENARIOS` pada `scripts/seed-demo.js`
dan di `scripts/deploy.js`.
