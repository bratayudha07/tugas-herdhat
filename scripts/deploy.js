const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

// Harus sama dengan enum Role di EHRTraceability.sol
const ROLE = {
  NONE: 0,
  RECEPTIONIST: 1,
  DOCTOR: 2,
  ADMIN: 3,
};

async function main() {
  const ContractFactory =
    await hre.ethers.getContractFactory("EHRTraceability");

  const contract = await ContractFactory.deploy();

  await contract.waitForDeployment();

  const address = await contract.getAddress();
  const { chainId } = await hre.ethers.provider.getNetwork();

  console.log("Deployment berhasil");
  console.log("Alamat kontrak:", address);

  // ==========================================
  // SEEDING PERAN
  // ==========================================
  // Admin otomatis diberikan di constructor (deployer). Resepsionis dan
  // dokter harus diberikan eksplisit supaya akun demo punya peran berbeda.

  const signers = await hre.ethers.getSigners();

  const [admin, receptionist, doctor, doctor2, patient] = signers;

  await (
    await contract.setRole(receptionist.address, ROLE.RECEPTIONIST)
  ).wait();
  await (await contract.setRole(doctor.address, ROLE.DOCTOR)).wait();
  await (await contract.setRole(doctor2.address, ROLE.DOCTOR)).wait();

  const doctors = await contract.getDoctors();

  console.log("\nPeran yang diberikan:");
  console.log("  admin        :", admin.address);
  console.log("  resepsionis  :", receptionist.address);
  console.log("  dokter       :", doctor.address);
  console.log("  dokter 2     :", doctor2.address);
  console.log("  pasien demo  :", patient.address);
  console.log("  getDoctors() :", doctors.length, "dokter terdaftar");

  // ==========================================
  // SIMPAN INFO DEPLOYMENT
  // ==========================================
  // Alamat kontrak dipakai aplikasi web. Daftar akun hanya petunjuk demo
  // (sumber kebenaran peran tetap getRole() di kontrak).

  const outFile = path.join(__dirname, "..", "deployment.json");

  fs.writeFileSync(
    outFile,
    JSON.stringify(
      {
        contract: "EHRTraceability",
        address: address,
        network: hre.network.name,
        chainId: Number(chainId),
        demoAccounts: {
          admin: admin.address,
          receptionist: receptionist.address,
          doctor: doctor.address,
          doctor2: doctor2.address,
          patient: patient.address,
        },
      },
      null,
      2
    )
  );

  console.log("\nInfo deployment disimpan ke:", outFile);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
