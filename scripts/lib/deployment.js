const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

const ROOT = path.join(__dirname, "..", "..");

// Urutan akun demo. Indeksnya dipakai `seed-demo.js` (1 = resepsionis,
// 2–3 = dokter, 4–7 = pasien), jadi jangan diubah tanpa menyesuaikan skenario.
const DEMO_ORDER = [
  "admin",
  "receptionist",
  "doctor",
  "doctor2",
  "patient",
  "patient2",
  "patient3",
  "patient4",
];

// Jaringan yang memakai akun bawaan Hardhat (node lokal). Selain ini, akun
// demo harus disiapkan sendiri karena node publik tidak memberi kita signer.
const LOCAL_NETWORKS = new Set(["localhost", "hardhat", "hardhat-in-process"]);

function isLocalNetwork() {
  return LOCAL_NETWORKS.has(hre.network.name);
}

/**
 * File info deployment per jaringan.
 *
 * Lokal tetap `deployment.json` supaya alur demo tidak berubah. Jaringan
 * publik memakai file sendiri (`deployment.sepolia.json`) supaya deploy ke
 * testnet tidak menimpa alamat kontrak lokal yang dipakai saat rekaman video.
 */
function deploymentPath(networkName = hre.network.name) {
  const name = LOCAL_NETWORKS.has(networkName)
    ? "deployment.json"
    : `deployment.${networkName}.json`;
  return path.join(ROOT, name);
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (error) {
    return fallback;
  }
}

function loadDeployment(networkName) {
  return readJson(deploymentPath(networkName), null);
}

function writeDeployment(networkName, data) {
  const file = deploymentPath(networkName);
  fs.writeFileSync(file, JSON.stringify(data, null, 2) + "\n");
  return file;
}

/**
 * Signer untuk seed demo.
 *
 * - Lokal: akun bawaan Hardhat (`getSigners()`), indeks sama seperti dulu.
 * - Publik: wallet dari private key demo yang tersimpan di file deployment.
 *   Kuncinya sengaja publik (testnet), jadi seed tetap bisa dijalankan tanpa
 *   menyentuh wallet pribadi siapa pun.
 */
async function demoSender(index, deployment) {
  if (isLocalNetwork()) {
    const signers = await hre.ethers.getSigners();
    return signers[index];
  }

  const key = deployment?.demoKeys?.[DEMO_ORDER[index]];
  if (!key) {
    throw new Error(
      `Private key akun demo ke-${index} tidak ada di file deployment. ` +
        "Jalankan deploy untuk jaringan ini dulu."
    );
  }

  return new hre.ethers.Wallet(key, hre.ethers.provider);
}

module.exports = {
  ROOT,
  DEMO_ORDER,
  isLocalNetwork,
  deploymentPath,
  loadDeployment,
  writeDeployment,
  demoSender,
};
