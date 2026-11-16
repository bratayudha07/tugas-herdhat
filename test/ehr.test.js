const { expect } = require("chai");
const { ethers } = require("hardhat");

// Role enum: 0 NONE, 1 RECEPTIONIST, 2 DOCTOR, 3 ADMIN
const NONE = 0n;
const RECEPTIONIST = 1n;
const DOCTOR = 2n;
const ADMIN = 3n;

// Status enum: 0 CREATED ... 4 COMPLETED
const CREATED = 0n;
const EXAMINED = 1n;
const DIAGNOSED = 2n;
const TREATED = 3n;
const COMPLETED = 4n;

const URI = "data:application/json;base64,e30=";

async function deploy() {
  const [admin, receptionist, doctor, doctor2, patient, stranger] =
    await ethers.getSigners();
  const Factory = await ethers.getContractFactory("EHRTraceability");
  const contract = await Factory.deploy();
  await contract.waitForDeployment();

  await contract.setRole(receptionist.address, RECEPTIONIST);
  await contract.setRole(doctor.address, DOCTOR);
  await contract.setRole(doctor2.address, DOCTOR);

  return { contract, admin, receptionist, doctor, doctor2, patient, stranger };
}

async function createSample(ctx) {
  const { contract, receptionist, doctor, patient } = ctx;
  await contract.connect(receptionist).createBatch(
    "P-001",
    "Budi Santoso",
    "Demam tiga hari",
    patient.address,
    doctor.address,
    URI
  );
  return 1n;
}

describe("EHRTraceability — peran & consent", function () {
  it("deployer otomatis ADMIN", async function () {
    const { contract, admin, receptionist } = await deploy();
    expect(await contract.getRole(admin.address)).to.equal(ADMIN);
    expect(await contract.getRole(receptionist.address)).to.equal(RECEPTIONIST);
  });

  it("hanya admin yang bisa memberi peran", async function () {
    const { contract, doctor, stranger } = await deploy();
    await expect(
      contract.connect(stranger).setRole(stranger.address, ADMIN)
    ).to.be.revertedWith("Hanya admin");
    expect(await contract.getRole(doctor.address)).to.equal(DOCTOR);
  });

  it("admin tidak bisa mengubah perannya sendiri", async function () {
    const { contract, admin } = await deploy();
    await expect(
      contract.connect(admin).setRole(admin.address, NONE)
    ).to.be.revertedWith("Admin tidak dapat mengubah perannya sendiri");
  });

  it("pasien/stranger tidak bisa membuat batch", async function () {
    const { contract, patient, stranger } = await deploy();
    await expect(
      contract.connect(patient).createBatch(
        "P-001", "Budi", "Demam", patient.address, patient.address, URI
      )
    ).to.be.revertedWith("Hanya resepsionis");

    await expect(
      contract.connect(stranger).createBatch(
        "P-001", "Budi", "Demam", patient.address, stranger.address, URI
      )
    ).to.be.revertedWith("Hanya resepsionis");
  });

  it("resepsionis membuat batch: NFT milik pasien, dokter tercatat", async function () {
    const ctx = await deploy();
    const { contract, receptionist, doctor, patient } = ctx;

    await expect(
      contract.connect(receptionist).createBatch(
        "P-001", "Budi Santoso", "Demam tiga hari",
        patient.address, doctor.address, URI
      )
    ).to.emit(contract, "BatchCreated").withArgs(1n, patient.address, "Budi Santoso");

    expect(await contract.ownerOf(1n)).to.equal(patient.address);
    expect(await contract.totalSupply()).to.equal(1n);

    const batch = await contract.getBatch(1n);
    expect(batch.patientId).to.equal("P-001");
    expect(batch.status).to.equal(CREATED);
    expect(batch.createdBy).to.equal(receptionist.address);
    expect(batch.doctor).to.equal(doctor.address);
    expect(batch.patient).to.equal(patient.address);
  });

  it("dokter tidak boleh menulis sebelum pasien setuju", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, doctor } = ctx;

    await expect(
      contract.connect(doctor).updateStatus(1n, EXAMINED)
    ).to.be.revertedWith("Pasien belum memberi izin");

    await expect(
      contract.connect(doctor).updateTreatment(1n, "Observasi", "Paracetamol")
    ).to.be.revertedWith("Pasien belum memberi izin");
  });

  it("hanya pasien pemilik yang bisa memberi/mencabut izin", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, receptionist, stranger } = ctx;

    await expect(
      contract.connect(receptionist).setConsent(1n, true)
    ).to.be.revertedWith("Hanya pasien pemilik rekam medis");

    await expect(
      contract.connect(stranger).setConsent(1n, true)
    ).to.be.revertedWith("Hanya pasien pemilik rekam medis");
  });

  it("setelah consent: dokter bisa majukan status & isi tindakan", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, patient, doctor } = ctx;

    await expect(contract.connect(patient).setConsent(1n, true))
      .to.emit(contract, "ConsentChanged")
      .withArgs(1n, doctor.address, true);

    await expect(contract.connect(doctor).updateStatus(1n, EXAMINED))
      .to.emit(contract, "StatusUpdated")
      .withArgs(1n, CREATED, EXAMINED);

    await contract.connect(doctor).updateTreatment(1n, "Observasi", "Paracetamol");

    const batch = await contract.getBatch(1n);
    expect(batch.status).to.equal(EXAMINED);
    expect(batch.treatment).to.equal("Observasi");
    expect(batch.medicine).to.equal("Paracetamol");
  });

  it("resepsionis tidak punya hak menulis data klinis", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, receptionist, patient } = ctx;
    await contract.connect(patient).setConsent(1n, true);

    await expect(
      contract.connect(receptionist).updateStatus(1n, EXAMINED)
    ).to.be.revertedWith("Bukan dokter");
  });

  it("dokter lain tidak bisa menulis walau sudah terdaftar", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, patient, doctor2 } = ctx;
    await contract.connect(patient).setConsent(1n, true);

    await expect(
      contract.connect(doctor2).updateStatus(1n, EXAMINED)
    ).to.be.revertedWith("Bukan dokter penanggung jawab");
  });

  it("status tidak boleh melompat atau mundur", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, patient, doctor } = ctx;
    await contract.connect(patient).setConsent(1n, true);

    await expect(
      contract.connect(doctor).updateStatus(1n, DIAGNOSED)
    ).to.be.revertedWith("Status tidak valid");
  });

  it("rekam medis soulbound: transfer ditolak", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, patient, stranger } = ctx;

    await expect(
      contract.connect(patient).transferFrom(patient.address, stranger.address, 1n)
    ).to.be.revertedWith("Rekam medis tidak dapat dipindahkan");

    await expect(
      contract.connect(patient)[
        "safeTransferFrom(address,address,uint256)"
      ](patient.address, stranger.address, 1n)
    ).to.be.revertedWith("Rekam medis tidak dapat dipindahkan");

    expect(await contract.ownerOf(1n)).to.equal(patient.address);
  });

  it("ganti dokter mencabut consent dokter lama", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, receptionist, patient, doctor, doctor2 } = ctx;

    await contract.connect(patient).setConsent(1n, true);
    expect(await contract.consent(1n, doctor.address)).to.equal(true);

    await expect(contract.connect(receptionist).assignDoctor(1n, doctor2.address))
      .to.emit(contract, "DoctorAssigned")
      .withArgs(1n, doctor2.address);

    expect(await contract.consent(1n, doctor.address)).to.equal(false);

    await expect(
      contract.connect(doctor).updateStatus(1n, EXAMINED)
    ).to.be.revertedWith("Bukan dokter penanggung jawab");

    // dokter baru butuh consent baru
    await expect(
      contract.connect(doctor2).updateStatus(1n, EXAMINED)
    ).to.be.revertedWith("Pasien belum memberi izin");

    await contract.connect(patient).setConsent(1n, true);
    await contract.connect(doctor2).updateStatus(1n, EXAMINED);
    expect((await contract.getBatch(1n)).status).to.equal(EXAMINED);
  });

  it("pasien bisa mencabut izin dan dokter langsung terblokir", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, patient, doctor } = ctx;

    await contract.connect(patient).setConsent(1n, true);
    await contract.connect(doctor).updateStatus(1n, EXAMINED);

    await contract.connect(patient).setConsent(1n, false);

    await expect(
      contract.connect(doctor).updateStatus(1n, DIAGNOSED)
    ).to.be.revertedWith("Pasien belum memberi izin");
  });

  it("treatment kosong ditolak, riwayat terbaru di atas", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, patient, doctor } = ctx;
    await contract.connect(patient).setConsent(1n, true);

    await expect(
      contract.connect(doctor).updateTreatment(1n, "", "")
    ).to.be.revertedWith("Isi tindakan atau obat");

    await contract.connect(doctor).updateStatus(1n, EXAMINED);

    const history = await contract.getHistory(1n);
    expect(history.length).to.equal(3n); // created, consent, status
    expect(history[0].action).to.equal("STATUS_UPDATED");
    expect(history[1].action).to.equal("CONSENT_GRANTED");
    expect(history[2].action).to.equal("BATCH_CREATED");
  });

  it("batch selesai tidak bisa diubah lagi", async function () {
    const ctx = await deploy();
    await createSample(ctx);
    const { contract, patient, doctor } = ctx;
    await contract.connect(patient).setConsent(1n, true);

    for (const step of [EXAMINED, DIAGNOSED, TREATED, COMPLETED]) {
      await contract.connect(doctor).updateStatus(1n, step);
    }

    await expect(
      contract.connect(doctor).updateStatus(1n, COMPLETED)
    ).to.be.revertedWith("Rekam medis sudah selesai");

    await expect(
      contract.connect(doctor).updateTreatment(1n, "X", "Y")
    ).to.be.revertedWith("Rekam medis sudah selesai");
  });

  it("alamat dokter harus terdaftar sebagai DOCTOR", async function () {
    const ctx = await deploy();
    const { contract, receptionist, patient, stranger } = ctx;

    await expect(
      contract.connect(receptionist).createBatch(
        "P-002", "Sari", "Nyeri dada", patient.address, stranger.address, URI
      )
    ).to.be.revertedWith("Alamat dokter tidak terdaftar");
  });

  it("batch tidak ditemukan memberi pesan jelas", async function () {
    const { contract } = await deploy();
    await expect(contract.getBatch(99n)).to.be.revertedWith("Batch tidak ditemukan");
  });
});

describe("EHRTraceability — daftar dokter", function () {
  it("mencatat dokter terdaftar dan mencabutnya saat peran dicabut", async function () {
    const { contract, doctor2 } = await deploy();

    let list = await contract.getDoctors();
    expect(list.length).to.equal(2);
    expect(list.map((a) => a.toLowerCase())).to.include(doctor2.address.toLowerCase());

    await contract.setRole(doctor2.address, NONE);

    list = await contract.getDoctors();
    expect(list.length).to.equal(1);
    expect(list.map((a) => a.toLowerCase())).to.not.include(doctor2.address.toLowerCase());

    // pencabutan ganda tidak merusak daftar
    await contract.setRole(doctor2.address, NONE);
    expect((await contract.getDoctors()).length).to.equal(1);
  });

  it("dokter yang dicabut tidak bisa dipakai untuk batch baru", async function () {
    const { contract, receptionist, patient, doctor2 } = await deploy();
    await contract.setRole(doctor2.address, NONE);

    await expect(
      contract.connect(receptionist).createBatch(
        "P-003", "Agus", "Pusing", patient.address, doctor2.address, URI
      )
    ).to.be.revertedWith("Alamat dokter tidak terdaftar");
  });
});
