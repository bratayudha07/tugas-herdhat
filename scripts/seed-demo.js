const hre = require("hardhat");
const {
  demoSender,
  deploymentPath,
  loadDeployment,
} = require("./lib/deployment");

// Harus sama dengan enum Status di EHRTraceability.sol
const STATUS = {
  CREATED: 0,
  EXAMINED: 1,
  DIAGNOSED: 2,
  TREATED: 3,
  COMPLETED: 4,
};

const STATUS_LABEL = [
  "CREATED",
  "EXAMINED",
  "DIAGNOSED",
  "TREATED",
  "COMPLETED",
];

// Skenario demo: sengaja beda-beda tahap supaya dashboard & filter ada isinya.
const SCENARIOS = [
  {
    patientId: "P-001",
    patientName: "Budi Santoso",
    complaint: "Demam tiga hari disertai pusing",
    patient: 4,
    doctor: 2,
    consent: true,
    treatment: "Pemeriksaan darah, istirahat 3 hari",
    medicine: "Paracetamol 3x500mg",
    steps: [
      STATUS.EXAMINED,
      STATUS.DIAGNOSED,
      STATUS.TREATED,
      STATUS.COMPLETED,
    ],
  },
  {
    patientId: "P-014",
    patientName: "Sari Dewi",
    complaint: "Nyeri dada saat menarik napas",
    patient: 5,
    doctor: 2,
    consent: true,
    treatment: "Rontgen toraks, observasi",
    medicine: "Ibuprofen 2x400mg",
    steps: [STATUS.EXAMINED, STATUS.DIAGNOSED, STATUS.TREATED],
  },
  {
    patientId: "P-009",
    patientName: "Agus Prakoso",
    complaint: "Batuk kering dua minggu",
    patient: 6,
    doctor: 3,
    consent: true,
    treatment: "Cek spirometri",
    medicine: "Salbutamol inhaler",
    steps: [STATUS.EXAMINED],
  },
  {
    patientId: "P-021",
    patientName: "Rina Marlina",
    complaint: "Sakit kepala berulang",
    patient: 7,
    doctor: 3,
    // sengaja belum setuju: untuk mendemokan dokter yang masih terblokir
    consent: false,
    treatment: "",
    medicine: "",
    steps: [],
  },
];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function errorText(error) {
  return String(
    error?.info?.error?.message ||
      error?.shortMessage ||
      error?.message ||
      error
  );
}

/**
 * Kirim transaksi dengan sedikit kesabaran.
 *
 * RPC publik (publicnode dkk.) itu load-balanced: receipt satu transaksi bisa
 * datang dari backend A, sementara `eth_estimateGas` untuk transaksi berikutnya
 * mendarat di backend B yang masih tertinggal satu blok. Gejalanya revert palsu
 * seperti "Pasien belum memberi izin" padahal consent-nya sudah true.
 * Karena itu pengiriman diulang beberapa kali, dan hanya untuk galat yang
 * memang biasanya sementara — revert logika kontrak tetap dilempar apa adanya.
 */
async function send(label, factory, attempts = 5) {
  let lastError;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    let tx;
    try {
      tx = await factory();
    } catch (error) {
      lastError = error;
      const message = errorText(error);
      const transient =
        /execution reverted|CALL_EXCEPTION|nonce|already known|timeout|429|503|502/i.test(
          message,
        );

      if (!transient || attempt === attempts) break;

      const wait = 2000 * attempt;
      console.log(
        `  ${label}: ${message.split("\n")[0].slice(0, 70)} — ` +
          `ulang dalam ${wait / 1000}s (${attempt}/${attempts})`,
      );
      await sleep(wait);
      continue;
    }

    return tx.wait();
  }

  throw lastError;
}

/** Cari tokenId yang sudah ada untuk patientId tertentu (null kalau belum). */
async function findTokenId(contract, patientId) {
  const total = await contract.totalSupply();

  for (let id = 1n; id <= total; id += 1n) {
    const batch = await contract.getBatch(id);
    if (batch.patientId === patientId) return id;
  }

  return null;
}

/**
 * Versi sabar dari `findTokenId`, dipakai setelah createBatch.
 *
 * RPC publik bisa menjawab `totalSupply` dari backend yang belum melihat blok
 * terbaru, jadi batch yang baru dibuat sempat "tidak ada". Dibaca ulang
 * beberapa kali sebelum dianggap gagal.
 */
async function waitForTokenId(contract, patientId, attempts = 6) {
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const tokenId = await findTokenId(contract, patientId);
    if (tokenId !== null) return tokenId;
    if (attempt < attempts) await sleep(2000);
  }

  return null;
}

async function main() {
  const deployment = loadDeployment();

  if (!deployment || !deployment.address) {
    throw new Error(
      "File deployment untuk jaringan ini belum ada. Jalankan deploy dulu: " +
        `npx hardhat run scripts/deploy.js --network ${hre.network.name} ` +
        `(dicari di ${deploymentPath()})`,
    );
  }

  const { address } = deployment;

  const contract = await hre.ethers.getContractAt("EHRTraceability", address);
  const receptionist = await demoSender(1, deployment);

  console.log("Seed data demo ke kontrak:", address);

  // Seed sengaja bisa dijalankan ulang: batch dicocokkan lewat patientId, dan
  // langkah yang sudah tercapai di chain dilewati. Jadi kalau jaringan putus di
  // tengah jalan, cukup jalankan perintah yang sama lagi — tidak ada data ganda.
  for (const scenario of SCENARIOS) {
    const patient = await demoSender(scenario.patient, deployment);
    const doctor = await demoSender(scenario.doctor, deployment);

    let tokenId = await findTokenId(contract, scenario.patientId);

    if (tokenId === null) {
      await send(`createBatch ${scenario.patientId}`, () =>
        contract
          .connect(receptionist)
          .createBatch(
            scenario.patientId,
            scenario.patientName,
            scenario.complaint,
            patient.address,
            doctor.address,
            ""
          )
      );

      tokenId = await waitForTokenId(contract, scenario.patientId);

      if (tokenId === null) {
        throw new Error(
          `Batch ${scenario.patientId} tidak ditemukan setelah dibuat.`
        );
      }
    }

    if (scenario.consent) {
      const granted = await contract.consent(tokenId, doctor.address);
      if (!granted) {
        await send(`setConsent ${scenario.patientId}`, () =>
          contract.connect(patient).setConsent(tokenId, true)
        );
      }
    }

    if (scenario.treatment || scenario.medicine) {
      const batch = await contract.getBatch(tokenId);
      const filled =
        batch.treatment === scenario.treatment &&
        batch.medicine === scenario.medicine;

      if (!filled) {
        await send(`updateTreatment ${scenario.patientId}`, () =>
          contract
            .connect(doctor)
            .updateTreatment(tokenId, scenario.treatment, scenario.medicine)
        );
      }
    }

    // Status hanya boleh naik satu langkah, jadi langkah yang sudah tercapai
    // dilewati (aman untuk dijalankan ulang).
    let current = Number((await contract.getBatch(tokenId)).status);

    for (const step of scenario.steps) {
      if (step <= current) continue;

      await send(
        `updateStatus ${scenario.patientId} → ${STATUS_LABEL[step]}`,
        () => contract.connect(doctor).updateStatus(tokenId, step)
      );

      current = step;
    }

    console.log(
      `  #${tokenId} ${scenario.patientName.padEnd(15)} ` +
        `consent=${scenario.consent ? "ya" : "belum"} ` +
        `status=${STATUS_LABEL[current]}`
    );
  }

  console.log(
    "\nSeed selesai. Total batch:",
    (await contract.totalSupply()).toString()
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
