/*
 * Koneksi wallet (MetaMask) untuk topbar & dashboard.
 *
 * Batas tanggung jawab: file ini hanya membaca alamat, chain, dan saldo.
 * Semua transaksi ditandatangani di wallet — private key tidak pernah
 * menyentuh server maupun file ini.
 */
document.addEventListener("alpine:init", () => {
  Alpine.data("walletBar", () => ({
    address: null,
    chainId: null,
    balance: null,
    busy: false,
    hasProvider: false,
    expectedChainId: 0,

    init() {
      const root = document.documentElement;
      this.expectedChainId = Number(root.dataset.expectedChainId || 0);
      this.hasProvider = Boolean(window.ethereum);

      if (!this.hasProvider) return;

      // Jangan memunculkan popup saat halaman dibuka.
      this.bootstrap();
    },

    async bootstrap() {
      window.ethereum.on?.("accountsChanged", (accounts) => {
        this.applyAccount(accounts[0] || null);
      });

      window.ethereum.on?.("chainChanged", (chainHex) => {
        this.chainId = Number(chainHex);
        this.loadBalance();
      });

      try {
        const accounts = await window.ethereum.request({
          method: "eth_accounts",
        });
        if (accounts.length) await this.applyAccount(accounts[0]);
      } catch (error) {
        console.warn("Gagal membaca akun wallet:", error);
      }
    },

    async connect() {
      if (!this.hasProvider) return;

      this.busy = true;
      try {
        const accounts = await window.ethereum.request({
          method: "eth_requestAccounts",
        });
        await this.applyAccount(accounts[0] || null);
      } catch (error) {
        // 4001 = user menutup dialog MetaMask, bukan error aplikasi.
        if (error?.code !== 4001) console.error(error);
      } finally {
        this.busy = false;
      }
    },

    async applyAccount(address) {
      this.address = address;

      if (!address) {
        this.chainId = null;
        this.balance = null;
        return;
      }

      try {
        const chainHex = await window.ethereum.request({
          method: "eth_chainId",
        });
        this.chainId = Number(chainHex);
        await this.loadBalance();
      } catch (error) {
        console.warn("Gagal membaca jaringan wallet:", error);
      }
    },

    async loadBalance() {
      if (!this.address || !this.hasProvider) {
        this.balance = null;
        return;
      }

      try {
        const weiHex = await window.ethereum.request({
          method: "eth_getBalance",
          params: [this.address, "latest"],
        });
        const eth = Number(BigInt(weiHex)) / 1e18;
        this.balance = eth.toLocaleString("id-ID", {
          maximumFractionDigits: 2,
        });
      } catch (error) {
        this.balance = null;
      }
    },

    wrongNetwork() {
      return Boolean(
        this.address &&
          this.expectedChainId &&
          this.chainId &&
          this.chainId !== this.expectedChainId,
      );
    },

    short() {
      if (!this.address) return "";
      return `${this.address.slice(0, 6)}…${this.address.slice(-4)}`;
    },
  }));
});
