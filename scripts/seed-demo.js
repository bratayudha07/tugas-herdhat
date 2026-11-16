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

  const existing = await contract.totalSupply();

  if (existing > 0n) {
    console.log(
      `Sudah ada ${existing} batch di kontrak. Seed dibatalkan supaya ` +
        "tidak menumpuk data ganda."
    );
    return;
  }

  const receptionist = await demoSender(1, deployment);

  console.log("Seed data demo ke kontrak:", address);

  for (const scenario of SCENARIOS) {
    const patient = await demoSender(scenario.patient, deployment);
    const doctor = await demoSender(scenario.doctor, deployment);

    await (
      await contract
        .connect(receptionist)
        .createBatch(
          scenario.patientId,
          scenario.patientName,
          scenario.complaint,
          patient.address,
          doctor.address,
          ""
        )
    ).wait();

    const tokenId = await contract.totalSupply();

    if (scenario.consent) {
      await (await contract.connect(patient).setConsent(tokenId, true)).wait();
    }

    if (scenario.treatment || scenario.medicine) {
      await (
        await contract
          .connect(doctor)
          .updateTreatment(tokenId, scenario.treatment, scenario.medicine)
      ).wait();
    }

    for (const step of scenario.steps) {
      await (await contract.connect(doctor).updateStatus(tokenId, step)).wait();
    }

    console.log(
      `  #${tokenId} ${scenario.patientName.padEnd(15)} ` +
        `consent=${scenario.consent ? "ya" : "belum"} ` +
        `status=${STATUS_LABEL[scenario.steps.length ? scenario.steps.at(-1) : 0]}`
    );
  }

  console.log("\nSeed selesai. Total batch:", (await contract.totalSupply()).toString());
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
