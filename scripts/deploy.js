const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  const ContractFactory =
    await hre.ethers.getContractFactory("EHRTraceability");

  const contract = await ContractFactory.deploy();

  await contract.waitForDeployment();

  const address = await contract.getAddress();
  const { chainId } = await hre.ethers.provider.getNetwork();

  console.log("Deployment berhasil");
  console.log("Alamat kontrak:", address);

  // Disimpan agar app.py (Streamlit) bisa membaca alamat kontrak terbaru.
  const outFile = path.join(__dirname, "..", "deployment.json");
  fs.writeFileSync(
    outFile,
    JSON.stringify(
      {
        contract: "EHRTraceability",
        address: address,
        network: hre.network.name,
        chainId: Number(chainId),
      },
      null,
      2
    )
  );
  console.log("Info deployment disimpan ke:", outFile);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
