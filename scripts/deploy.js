const hre = require("hardhat");

async function main() {
  const ContractFactory =
    await hre.ethers.getContractFactory("EHRTraceability");

  const contract = await ContractFactory.deploy();

  await contract.waitForDeployment();

  console.log("Deployment berhasil");
  console.log("Alamat kontrak:", await contract.getAddress());
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
