require("@nomicfoundation/hardhat-toolbox");

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    compilers: [
      {
        version: "0.8.28",
        settings: {
          evmVersion: "cancun",
          optimizer: {
            enabled: true,
            runs: 200
          }
        }
      }
    ]
  },
  networks: {
    localhost: {
      url: "http://127.0.0.1:8545",
      chainId: 31337,
    },
    // Testnet publik. RPC bisa dioverride lewat env; default-nya endpoint
    // publik tanpa API key supaya deploy tetap bisa dicoba tanpa daftar.
    // Untuk aplikasi yang dipakai orang banyak, pakai RPC ber-API-key
    // (Alchemy/Infura) — endpoint publik dipakai bersama dan mudah kena 429.
    sepolia: {
      url:
        process.env.SEPOLIA_RPC_URL ||
        "https://ethereum-sepolia-rpc.publicnode.com",
      chainId: 11155111,
    },
  }
};
