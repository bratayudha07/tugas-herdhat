/*
 * Komponen dua halaman akun:
 *
 * - `walletPage`  → /wallet      : identitas wallet, saldo dari RPC, riwayat sesi.
 * - `accessPage`  → /hak-akses   : tabel izin dokter per batch.
 *
 * Keduanya membaca state wallet dari `Alpine.store("wallet")`, jadi tidak ada
 * alamat wallet yang disimpan sendiri-sendiri di DOM.
 */
(() => {
  const { getJSON } = window.ehrApi;
  const wallet = () => Alpine.store("wallet");
  // Mesin transaksi bersama (dialog, panel, polling) milik `tx.js`.
  const txMachine = () => window.ehrTx.txMachine();

  function shortAddr(address) {
    if (!address) return "—";
    return `${address.slice(0, 6)}…${address.slice(-4)}`;
  }

  /** Salin teks; clipboard API bisa ditolak (izin/konteks), jadi ada cadangan. */
  async function copyText(text) {
    if (!text) return false;

    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (ignored) {
        ok = false;
      }
      area.remove();
      return ok;
    }
  }

  document.addEventListener("alpine:init", () => {
    Alpine.data("walletPage", () => ({
      account: null,
      loading: false,
      error: "",
      copied: "",
      note: "",
      history: [],
      demo: [],
      demoLoading: false,
      demoNetwork: "",

      init() {
        this.history = window.ehrSession.list();
        this.$watch(
          () => wallet().address,
          () => {
            this.history = window.ehrSession.list();
            this.load();
          },
        );
        this.load();
        // Akun demo tidak bergantung pada wallet yang tersambung.
        this.loadDemo();
      },

      // --- state turunan ----------------------------------------------

      address() {
        return wallet().address;
      },

      mode() {
        if (!wallet().hasProvider) return "no-provider";
        if (!wallet().address) return "no-wallet";
        return "ready";
      },

      roleLabel() {
        return this.account ? this.account.roleLabel : "—";
      },

      balanceText() {
        if (!this.account || this.account.balance === null) return "—";
        return `${Number(this.account.balance).toLocaleString("id-ID", {
          maximumFractionDigits: 4,
        })} ETH`;
      },

      gasText() {
        if (!this.account || this.account.gasPrice === null) return "—";
        return `${Number(this.account.gasPrice).toLocaleString("id-ID", {
          maximumFractionDigits: 2,
        })} gwei`;
      },

      chainText() {
        const id = wallet().chainId ?? this.account?.chainId ?? null;
        return id === null ? "—" : `Chain ${id}`;
      },

      chainMatches() {
        const expected = wallet().expectedChainId;
        if (!expected || !wallet().chainId) return null;
        return wallet().chainId === expected;
      },

      scopeNote() {
        if (!this.account) return "";
        if (this.account.role === "PATIENT") {
          return `Pemilik ${this.account.ownedBatches} batch rekam medis.`;
        }
        if (this.account.role === "DOCTOR") {
          return `${this.account.assignedBatches} batch ditugaskan ke wallet ini.`;
        }
        return "";
      },

      // --- aksi -------------------------------------------------------

      async load() {
        if (!wallet().address) {
          this.account = null;
          this.error = "";
          return;
        }

        this.loading = true;
        try {
          const response = await getJSON(
            `/api/account?address=${encodeURIComponent(wallet().address)}`,
          );
          if (response.ok) {
            this.account = response.data;
            this.error = "";
          } else {
            this.account = null;
            this.error = response.data.error || "Gagal membaca data wallet.";
          }
        } finally {
          this.loading = false;
        }
      },

      async copy(text, key = "address") {
        const ok = await copyText(text);
        this.copied = ok ? key : "";
        this.note = ok ? "" : "Browser menolak akses clipboard — salin manual dari teks di atas.";
        if (ok) {
          setTimeout(() => {
            if (this.copied === key) this.copied = "";
          }, 1600);
        }
      },

      async switchAccount() {
        this.note = "";
        const ok = await wallet().switchAccount();
        if (!ok) this.note = "Tidak ada akun yang dipilih. Coba lagi dari MetaMask.";
      },

      async switchNetwork() {
        this.note = "";
        try {
          await wallet().ensureChain();
          await this.load();
        } catch (error) {
          this.note = "Jaringan tidak bisa diganti dari sini. Ganti manual di MetaMask.";
        }
      },

      async disconnect() {
        const result = await wallet().revoke();
        this.account = null;
        this.note = result.supported
          ? "Izin situs dicabut di MetaMask. Halaman ini tidak lagi memegang alamat wallet."
          : "MetaMask versi ini tidak mendukung pencabutan izin dari halaman. Putuskan lewat menu ekstensi.";
      },

      clearHistory() {
        window.ehrSession.clear();
        this.history = [];
      },

      // --- akun demo testnet -------------------------------------------

      async loadDemo() {
        this.demoLoading = true;
        try {
          const response = await getJSON("/api/demo");
          if (response.ok) {
            this.demo = response.data.accounts || [];
            this.demoNetwork = response.data.network || "";
          } else {
            this.demo = [];
          }
        } catch (error) {
          this.demo = [];
        } finally {
          this.demoLoading = false;
        }
      },

      /** Link faucet untuk jaringan yang sedang dipakai (kalau ada). */
      faucetUrl() {
        const links = {
          Sepolia: "https://cloud.google.com/application/web3/faucet/ethereum/sepolia",
          "Base Sepolia": "https://www.alchemy.com/faucets/base-sepolia",
          "Arbitrum Sepolia": "https://faucet.quicknode.com/arbitrum/sepolia",
        };
        return links[this.demoNetwork] || "";
      },

      short(address) {
        return shortAddr(address);
      },

      /** Ada akun demo yang kuncinya dibagikan? Kalau tidak, kartu disembunyikan. */
      demoShared() {
        return this.demo.some((row) => row.privateKey);
      },

      demoBalance(row) {
        if (row.balance === null || row.balance === undefined) return "—";
        return `${Number(row.balance).toLocaleString("id-ID", {
          maximumFractionDigits: 4,
        })} ETH`;
      },

      demoScope(row) {
        if (row.ownedBatches) return `pemilik ${row.ownedBatches} batch`;
        if (row.assignedBatches) return `${row.assignedBatches} batch ditugaskan`;
        return "";
      },

      // --- riwayat sesi -----------------------------------------------

      fmtTime(value) {
        if (!value) return "";
        return new Date(value).toLocaleString("id-ID", {
          dateStyle: "short",
          timeStyle: "short",
        });
      },

      txMeta(entry) {
        if (entry.state === "failed") {
          return `gagal · ${entry.reason || "reverted"}`;
        }
        const parts = [];
        if (entry.block !== null && entry.block !== undefined) parts.push(`blok ${entry.block}`);
        if (entry.gas) parts.push(`gas ${Number(entry.gas).toLocaleString("id-ID")}`);
        return parts.join(" · ") || "berhasil";
      },

      txState(entry) {
        return entry.state === "failed" ? "Gagal" : "Berhasil";
      },
    }));

    Alpine.data("accessPage", () =>
      Object.assign(txMachine(), {
        role: "",
        roleLabel: "",
        rows: [],
        counts: { total: 0, active: 0, waiting: 0 },
        doctors: [],
        accounts: [],
        loading: false,
        error: "",

        init() {
          this.$watch(
            () => wallet().address,
            () => this.load(),
          );
          this.load();
        },

        destroy() {
          this.clearTx();
        },

        // --- state turunan --------------------------------------------

        mode() {
          if (!wallet().hasProvider) return "no-provider";
          if (!wallet().address) return "no-wallet";
          if (this.error) return "error";
          if (this.loading && !this.rows.length) return "loading";
          return "ready";
        },

        short(address) {
          return shortAddr(address);
        },

        emptyText() {
          if (this.role === "PATIENT") {
            return "Wallet ini belum memiliki batch rekam medis.";
          }
          if (this.role === "DOCTOR") {
            return "Belum ada batch yang menugaskan wallet ini sebagai dokter penanggung jawab.";
          }
          return "Belum ada batch di kontrak.";
        },

        consentText(row) {
          if (!row.doctor) return "Dokter belum ditetapkan";
          if (row.consent === null) return "Tidak terbaca";
          if (row.completed) return row.consent ? "Aktif (final)" : "Tidak pernah diberikan";
          return row.consent ? "Aktif" : "Belum ada";
        },

        consentState(row) {
          if (!row.doctor) return "warn";
          if (row.consent === null) return "warn";
          return row.consent ? "ok" : "warn";
        },

        actionLabel(row) {
          // Batch COMPLETED tidak bisa diubah lagi — tombolnya jangan
          // menjanjikan aksi yang akan ditolak kontrak.
          if (row.completed) return "Lihat";
          if (this.role === "RECEPTIONIST") return "Ganti dokter";
          if (this.role === "DOCTOR") return "Buka";
          return "Lihat";
        },

        // --- data ------------------------------------------------------

        async load() {
          if (!wallet().address) {
            this.rows = [];
            this.accounts = [];
            this.error = "";
            return;
          }

          this.loading = true;
          try {
            const response = await getJSON(
              `/api/access?address=${encodeURIComponent(wallet().address)}`,
            );
            if (response.ok) {
              this.role = response.data.role;
              this.roleLabel = response.data.roleLabel;
              this.rows = response.data.rows || [];
              this.counts = response.data.counts || this.counts;
              this.doctors = response.data.doctors || [];
              this.accounts = response.data.accounts || [];
              this.error = "";
            } else {
              this.rows = [];
              this.accounts = [];
              this.error = response.data.error || "Gagal membaca data izin.";
            }
          } finally {
            this.loading = false;
          }
        },

        // --- aksi ------------------------------------------------------

        grant(row) {
          return this.prepare("setConsent", { tokenId: row.tokenId, granted: true });
        },

        revoke(row) {
          return this.prepare("setConsent", { tokenId: row.tokenId, granted: false });
        },

        async onTxSuccess() {
          // Izin baru sudah masuk chain — tabel dibaca ulang supaya chip dan
          // tombol tidak menampilkan state sebelum transaksi.
          await this.load();
        },
      }),
    );
  });
})();
