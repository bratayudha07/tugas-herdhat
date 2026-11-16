/*
 * Salin ABI dari artifact Hardhat ke `web/abi.json`.
 *
 * Kenapa perlu: folder `artifacts/` tidak ikut di-commit (isinya bytecode
 * debug dan besar), padahal aplikasi web butuh ABI saat runtime. File
 * `web/abi.json` yang kecil ini yang di-commit, jadi deploy ke hosting tetap
 * bisa membaca kontrak tanpa menjalankan `npx hardhat compile` di server.
 *
 * Jalankan setelah kontrak berubah:
 *   npx hardhat compile && npm run abi
 */
const fs = require("fs");
const path = require("path");

const ARTIFACT = path.join(
  __dirname,
  "..",
  "artifacts",
  "contracts",
  "EHRTraceability.sol",
  "EHRTraceability.json",
);
const TARGET = path.join(__dirname, "..", "web", "abi.json");

function main() {
  if (!fs.existsSync(ARTIFACT)) {
    console.error(
      "Artifact belum ada. Jalankan `npx hardhat compile` dulu.\n" +
        "Dicari di: " + ARTIFACT,
    );
    process.exit(1);
  }

  const artifact = JSON.parse(fs.readFileSync(ARTIFACT, "utf8"));
  const abi = artifact.abi || [];

  if (!abi.length) {
    console.error("Artifact tidak punya `abi` — kompilasi gagal?");
    process.exit(1);
  }

  fs.writeFileSync(TARGET, JSON.stringify(abi, null, 2) + "\n");

  const events = abi.filter((item) => item.type === "event").length;
  const fns = abi.filter((item) => item.type === "function").length;
  console.log(`ABI ditulis ke ${TARGET} (${fns} fungsi, ${events} event).`);
}

main();
