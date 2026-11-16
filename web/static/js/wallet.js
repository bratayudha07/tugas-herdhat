/*
 * Koneksi wallet (MetaMask) + catatan transaksi sesi ini.
 *
 * Batas tanggung jawab: file ini hanya membaca alamat, chain, dan saldo,
 * serta menyimpan **hash** transaksi yang sudah ditandatangani. Tidak ada
 * private key di sini dan tidak ada tanda tangan di sini.
 *
 * Store `wallet` adalah pemilik state; `walletBar` di base.html hanya
 * meneruskan ke template. Halaman lain (Wallet, Hak Akses, form transaksi)
 * membaca store yang sama, jadi tidak ada dua sumber alamat wallet.
 */
(() => {
  const SESSION_KEY = "ehr.txlog.v1";
  const SESSION_LIMIT = 20;

  const chainHex = (id) => "0x" + Number(id).toString(16);

  function shortAddr(address) {
    if (!address) return "";
    return `${address.slice(0, 6)}…${address.slice(-4)}`;
  }

  /**
   * Riwayat transaksi sesi ini (localStorage, bukan chain).
   * Hanya transaksi yang sampai ke node yang dicatat — penolakan MetaMask
   * tidak punya hash, jadi tidak ada yang bisa ditampilkan.
   */
  window.ehrSession = {
    list() {
      try {
        const raw = localStorage.getItem(SESSION_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        return [];
      }
    },

    add(entry) {
      const next = [{ ...entry, at: Date.now() }, ...this.list()].slice(0, SESSION_LIMIT);
      try {
        localStorage.setItem(SESSION_KEY, JSON.stringify(next));
      } catch (error) {
        // Mode privat / kuota penuh: riwayat hilang, transaksi tetap sah.
      }
      return next;
    },

    clear() {
      try {
        localStorage.removeItem(SESSION_KEY);
      } catch (error) {
        /* tidak ada yang bisa dilakukan */
      }
    },
  };

  document.addEventListener("alpine:init", () => {
    Alpine.store("wallet", {
      address: null,
      chainId: null,
      balance: null,
      hasProvider: false,
      expectedChainId: 0,
      busy: false,
      error: "",

      init() {
        const root = document.documentElement;
        this.expectedChainId = Number(root.dataset.expectedChainId || 0);
        this.hasProvider = Boolean(window.ethereum);
        if (!this.hasProvider) return;

        window.ethereum.on?.("accountsChanged", (accounts) => {
          this.applyAccount(accounts[0] || null);
        });

        window.ethereum.on?.("chainChanged", (value) => {
          this.chainId = Number(value);
          this.loadBalance();
        });

        // Jangan memunculkan popup saat halaman dibuka.
        this.bootstrap();
      },

      async bootstrap() {
        try {
          const accounts = await window.ethereum.request({ method: "eth_accounts" });
          if (accounts.length) await this.applyAccount(accounts[0]);
        } catch (error) {
          console.warn("Gagal membaca akun wallet:", error);
        }
      },

      async connect() {
        if (!this.hasProvider) return false;

        this.busy = true;
        try {
          const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
          await this.applyAccount(accounts[0] || null);
          return true;
        } catch (error) {
          // 4001 = user menutup dialog MetaMask, bukan error aplikasi.
          if (error?.code !== 4001) {
            this.error = "Wallet menolak permintaan koneksi.";
            console.error(error);
          }
          return false;
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
          const value = await window.ethereum.request({ method: "eth_chainId" });
          this.chainId = Number(value);
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
          this.balance = Number(BigInt(weiHex)) / 1e18;
        } catch (error) {
          this.balance = null;
        }
      },

      /** Pastikan wallet memakai chain yang sama dengan RPC server. */
      async ensureChain() {
        const expected = this.expectedChainId;
        if (!expected || this.chainId === expected) return true;
        if (!this.hasProvider) throw new Error("MetaMask tidak tersedia");

        try {
          await window.ethereum.request({
            method: "wallet_switchEthereumChain",
            params: [{ chainId: chainHex(expected) }],
          });
        } catch (error) {
          if (error?.code !== 4902) throw error;

          await window.ethereum.request({
            method: "wallet_addEthereumChain",
            params: [
              {
                chainId: chainHex(expected),
                chainName: document.documentElement.dataset.chainName || "Hardhat Local",
                rpcUrls: [document.documentElement.dataset.rpcUrl],
                nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
              },
            ],
          });
        }

        this.chainId = expected;
        return true;
      },

      /** Buka pemilih akun MetaMask, lalu sinkronkan alamat yang dipilih. */
      async switchAccount() {
        if (!this.hasProvider) return false;

        try {
          await window.ethereum.request({
            method: "wallet_requestPermissions",
            params: [{ eth_accounts: {} }],
          });
        } catch (error) {
          if (error?.code === 4001) return false; // user membatalkan
        }

        try {
          const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
          await this.applyAccount(accounts[0] || null);
          return true;
        } catch (error) {
          return false;
        }
      },

      /**
       * Lepaskan izin situs ini di MetaMask.
       *
       * MetaMask lama tidak punya `wallet_revokePermissions`; kalau metode itu
       * ditolak, state lokal tetap dibersihkan dan halaman menjelaskan bahwa
       * pencabutan harus dilakukan dari ekstensi.
       */
      async revoke() {
        if (!this.hasProvider) return { revoked: false, supported: false };

        let supported = false;
        try {
          await window.ethereum.request({
            method: "wallet_revokePermissions",
            params: [{ eth_accounts: {} }],
          });
          supported = true;
        } catch (error) {
          supported = false;
        }

        this.address = null;
        this.chainId = null;
        this.balance = null;
        return { revoked: true, supported };
      },

      short() {
        return shortAddr(this.address);
      },

      wrongNetwork() {
        return Boolean(
          this.address &&
            this.expectedChainId &&
            this.chainId &&
            this.chainId !== this.expectedChainId,
        );
      },
    });

    // Topbar: pembungkus tipis supaya template tidak perlu menulis `$store`.
    Alpine.data("walletBar", () => ({
      get address() {
        return this.$store.wallet.address;
      },
      get busy() {
        return this.$store.wallet.busy;
      },
      get hasProvider() {
        return this.$store.wallet.hasProvider;
      },
      connect() {
        return this.$store.wallet.connect();
      },
      short() {
        return this.$store.wallet.short();
      },
      wrongNetwork() {
        return this.$store.wallet.wrongNetwork();
      },
    }));
  });
})();
