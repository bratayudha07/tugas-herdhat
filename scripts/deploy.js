const hre = require("hardhat");
const {
  DEMO_ORDER,
  isLocalNetwork,
  loadDeployment,
  writeDeployment,
} = require("./lib/deployment");

// Harus sama dengan enum Role di EHRTraceability.sol
const ROLE = {
  NONE: 0,
  RECEPTIONIST: 1,
  DOCTOR: 2,
  ADMIN: 3,
};

// Jumlah ETH yang dikirim ke tiap akun demo di jaringan publik supaya mereka
// bisa mengirim transaksi sendiri (pasien memberi izin, dokter mengisi data).
// Kecil dengan sengaja: kalau kuncinya disapu bot testnet, kerugiannya nol.
const FUND_AMOUNT = hre.ethers.parseEther("0.02");

/**
 * Siapkan akun demo untuk jaringan publik.
 *
 * Node publik tidak memberi kita 8 signer seperti Hardhat, jadi akun demo
 * dibuat sendiri. Private key-nya **sengaja** ikut ditulis ke file deployment
 * karena halaman web menampilkannya supaya pengunjung bisa mencoba menulis
 * transaksi. Hanya untuk testnet — nilainya nol dan tidak boleh dipakai untuk
 * apa pun yang nyata.
 */
function ensureDemoAccounts() {
  const existing = loadDeployment() || {};
  const accounts = { ...(existing.demoAccounts || {}) };
  const keys = { ...(existing.demoKeys || {}) };
  const generated = [];

  for (const name of DEMO_ORDER) {
    if (keys[name]) {
      accounts[name] =
        accounts[name] || new hre.ethers.Wallet(keys[name]).address;
      continue;
    }

    const wallet = hre.ethers.Wallet.createRandom();
    accounts[name] = wallet.address;
    keys[name] = wallet.privateKey;
    generated.push({ name, wallet });
  }

  return {
    generated,
    data: {
      ...existing,
      contract: "EHRTraceability",
      network: hre.network.name,
      address: existing.address || "",
      chainId: Number(existing.chainId || 0),
      demoAccounts: accounts,
      demoKeys: keys,
    },
  };
}

async function main() {
  if (!isLocalNetwork()) {
    await deployPublic();
    return;
  }

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

  const outFile = writeDeployment(hre.network.name, {
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
  });

  console.log("\nInfo deployment disimpan ke:", outFile);
}

/**
 * Deploy ke testnet publik memakai akun demo buatan sendiri.
 *
 * Dua langkah, sengaja:
 * 1. Kalau saldo akun admin masih nol, skrip berhenti dan hanya mencetak
 *    alamat yang perlu diisi dari faucet. Tidak ada transaksi yang terbuang.
 * 2. Setelah ada saldo, skrip mendeploy, memberi peran, lalu mengirim sedikit
 *    ETH ke akun demo lain supaya tombol di UI benar-benar bisa dipakai.
 */
async function deployPublic() {
  const prepared = ensureDemoAccounts();
  const data = prepared.data;

  if (prepared.generated.length) {
    console.log("Akun demo baru dibuat (hanya testnet, kuncinya publik):\n");
    for (const item of prepared.generated) {
      console.log(`  ${item.name.padEnd(13)} ${item.wallet.address}`);
    }
    console.log("");
  }

  const admin = new hre.ethers.Wallet(data.demoKeys.admin, hre.ethers.provider);
  const balance = await hre.ethers.provider.getBalance(admin.address);

  if (balance === 0n) {
    const file = writeDeployment(hre.network.name, data);
    console.log("Saldo akun admin masih 0. Isi dulu dari faucet:\n");
    console.log(`  admin (deployer) : ${admin.address}`);
    console.log(
      "  faucet Sepolia   : https://cloud.google.com/application/web3/faucet/ethereum/sepolia",
    );
    console.log("\nSetelah ada saldo, jalankan perintah yang sama lagi.");
    console.log("Akun demo disimpan di:", file);
    return;
  }

  const ContractFactory = await hre.ethers.getContractFactory(
    "EHRTraceability",
    admin,
  );
  const contract = await ContractFactory.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  const { chainId } = await hre.ethers.provider.getNetwork();

  console.log("Deployment berhasil:", address);

  // Resepsionis + 2 dokter mendapat peran; pasien cukup memiliki NFT.
  await (
    await contract.setRole(data.demoAccounts.receptionist, ROLE.RECEPTIONIST)
  ).wait();
  await (await contract.setRole(data.demoAccounts.doctor, ROLE.DOCTOR)).wait();
  await (await contract.setRole(data.demoAccounts.doctor2, ROLE.DOCTOR)).wait();

  for (const name of DEMO_ORDER.slice(1)) {
    const target = data.demoAccounts[name];
    const targetBalance = await hre.ethers.provider.getBalance(target);
    if (targetBalance >= FUND_AMOUNT) continue;

    const tx = await admin.sendTransaction({ to: target, value: FUND_AMOUNT });
    await tx.wait();
    console.log(`  dana ${name.padEnd(13)} ${target} +0.02 ETH`);
  }

  const file = writeDeployment(hre.network.name, {
    ...data,
    address,
    chainId: Number(chainId),
  });

  console.log("\nPeran & alamat:");
  for (const name of DEMO_ORDER) {
    console.log(`  ${name.padEnd(13)} ${data.demoAccounts[name]}`);
  }
  console.log("\nInfo deployment disimpan ke:", file);
  console.log(
    "Langkah berikutnya: seed data demo →\n" +
      `  npx hardhat run scripts/seed-demo.js --network ${hre.network.name}`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
