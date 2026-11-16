/*
 * Mesin transaksi di browser: validasi server → konfirmasi → MetaMask →
 * pantau receipt.
 *
 * Server hanya menyiapkan `to` + `data`; tanda tangan terjadi di wallet.
 * Private key tidak pernah dikirim ke server maupun disimpan di file ini.
 */
(() => {
  const POLL_INTERVAL = 2000;
  const POLL_TIMEOUT = 60000;

  const wallet = () => Alpine.store("wallet");

  const chainHex = (id) => "0x" + Number(id).toString(16);

  function shortHash(hash) {
    if (!hash) return "";
    return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
  }

  function fmtNumber(value) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString("id-ID");
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return { ok: response.ok, status: response.status, data: await readJSON(response) };
  }

  async function getJSON(url) {
    const response = await fetch(url);
    return { ok: response.ok, status: response.status, data: await readJSON(response) };
  }

  async function readJSON(response) {
    try {
      return (await response.json()) || {};
    } catch (error) {
      return {};
    }
  }

  /**
   * Pastikan MetaMask memakai chain yang sama dengan RPC server.
   * Kalau chain-nya belum ada di wallet, tawarkan penambahan otomatis.
   */
  async function ensureChain() {
    const expected = wallet().expectedChainId;
    if (!expected || wallet().chainId === expected) return true;

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
            chainName: "Hardhat Local",
            rpcUrls: [document.documentElement.dataset.rpcUrl],
            nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
          },
        ],
      });
    }

    wallet().chainId = expected;
    return true;
  }

  document.addEventListener("alpine:init", () => {
    Alpine.data("createBatchForm", () => ({
      // isi form
      patientId: "",
      patientName: "",
      complaint: "",
      patient: "",
      doctor: "",
      metadata: "",
      showMeta: false,

      // mesin status
      phase: "idle", // idle | building | ready | signing | pending | success | failed | rejected | timeout | error | invalid
      errors: {},
      banner: "",
      role: null,
      roleLoading: false,
      tx: null,
      hash: "",
      result: null,
      lastTokenId: null,
      confirmOpen: false,
      pollTimer: null,
      startedAt: 0,

      init() {
        // $watch dipakai supaya form ikut berubah saat user ganti akun di
        // MetaMask, tanpa polling.
        this.$watch(
          () => wallet().address,
          (address) => this.loadRole(address),
        );
        this.loadRole(wallet().address);
      },

      destroy() {
        clearTimeout(this.pollTimer);
      },

      // --- data turunan -------------------------------------------------

      address() {
        return wallet().address;
      },

      short(addr) {
        if (!addr) return "—";
        return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
      },

      gate() {
        if (!wallet().hasProvider) return "no-provider";
        if (!wallet().address) return "no-wallet";
        if (this.roleLoading || !this.role) return "checking";
        return this.role.role === "RECEPTIONIST" ? "open" : "blocked";
      },

      busy() {
        return ["building", "signing", "pending"].includes(this.phase);
      },

      complaintLeft() {
        return 280 - this.complaint.length;
      },

      statusText() {
        switch (this.phase) {
          case "pending":
            return `Menunggu konfirmasi… (hash ${shortHash(this.hash)})`;
          case "success":
            return this.result
              ? `Transaksi berhasil · blok ${this.result.block} · gas ${fmtNumber(this.result.gas)}`
              : "Transaksi berhasil.";
          case "failed":
            return `Transaksi gagal: ${this.result?.reason || "reverted"}`;
          case "rejected":
            return "Kamu membatalkan transaksi di MetaMask.";
          case "timeout":
            return "Belum dikonfirmasi setelah 60 detik. Cek daftar batch — kalau sudah masuk, datanya muncul.";
          case "error":
            return this.banner;
          default:
            return "";
        }
      },

      panelTone() {
        if (this.phase === "success") return "ok";
        if (["failed", "error", "invalid"].includes(this.phase)) return "bad";
        if (["pending", "signing", "timeout", "rejected"].includes(this.phase)) {
          return "warn";
        }
        return "info";
      },

      panelVisible() {
        return ["pending", "success", "failed", "rejected", "timeout", "error"].includes(
          this.phase,
        );
      },

      // --- peran --------------------------------------------------------

      async loadRole(address) {
        if (!address) {
          this.role = null;
          return;
        }

        this.roleLoading = true;
        try {
          const response = await getJSON(
            `/api/role?address=${encodeURIComponent(address)}`,
          );
          this.role = response.ok ? response.data : null;
        } finally {
          this.roleLoading = false;
        }
      },

      // --- alur transaksi ----------------------------------------------

      async submit() {
        if (this.gate() !== "open" || this.busy()) return;

        this.errors = {};
        this.banner = "";
        this.result = null;
        this.hash = "";
        this.lastTokenId = null;
        this.phase = "building";

        const response = await postJSON("/api/tx/build", {
          action: "createBatch",
          from: wallet().address,
          args: {
            patientId: this.patientId,
            patientName: this.patientName,
            complaint: this.complaint,
            patient: this.patient,
            doctor: this.doctor,
            metadata: this.showMeta ? this.metadata : "",
          },
        });

        if (!response.ok) {
          this.phase = "invalid";
          this.errors = response.data.fields || {};
          this.banner = response.data.error || "Gagal menyiapkan transaksi.";
          this.$nextTick(() => this.$refs.summary?.focus());
          return;
        }

        this.tx = response.data;
        this.phase = "ready";
        this.confirmOpen = true;
        this.$nextTick(() => this.$refs.confirmBtn?.focus());
      },

      closeConfirm() {
        this.confirmOpen = false;
        this.phase = this.tx ? "ready" : "idle";
        this.$nextTick(() => this.$refs.submitBtn?.focus());
      },

      revealPanel() {
        this.$nextTick(() =>
          this.$refs.panel?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
        );
      },

      async send() {
        if (!this.tx) return;
        this.confirmOpen = false;
        this.phase = "signing";
        this.banner = "";

        try {
          await ensureChain();
        } catch (error) {
          this.phase = "error";
          this.banner =
            "Jaringan wallet tidak cocok dengan RPC. Ganti jaringan di MetaMask, lalu ulangi.";
          return;
        }

        let hash;
        try {
          hash = await window.ethereum.request({
            method: "eth_sendTransaction",
            params: [{ from: this.tx.from, to: this.tx.to, data: this.tx.data }],
          });
        } catch (error) {
          if (error?.code === 4001) {
            this.phase = "rejected";
            this.revealPanel();
            return;
          }
          this.phase = "error";
          this.banner = `Wallet menolak transaksi: ${error?.message || "tanpa keterangan"}`;
          this.revealPanel();
          return;
        }

        this.hash = hash;
        this.phase = "pending";
        this.startedAt = Date.now();
        this.pollTimer = setTimeout(() => this.checkStatus(), POLL_INTERVAL);
      },

      async checkStatus() {
        if (this.phase !== "pending") return;

        const response = await getJSON(`/api/tx/${this.hash}`);
        if (!response.ok) {
          this.phase = "error";
          this.banner = response.data.error || "Gagal membaca status transaksi.";
          this.revealPanel();
          return;
        }

        if (response.data.state === "pending") {
          if (Date.now() - this.startedAt > POLL_TIMEOUT) {
            this.phase = "timeout";
            this.revealPanel();
            return;
          }
          this.pollTimer = setTimeout(() => this.checkStatus(), POLL_INTERVAL);
          return;
        }

        this.result = response.data;
        if (response.data.state === "success") {
          this.phase = "success";
          this.lastTokenId = response.data.tokenId;
        } else {
          this.phase = "failed";
        }
        this.revealPanel();
      },

      // Kirim ulang transaksi yang sudah disiapkan (mis. setelah user menolak
      // di MetaMask) — tidak perlu validasi ulang, calldata masih sama.
      retry() {
        if (!this.tx) {
          this.reset();
          return;
        }
        this.banner = "";
        this.phase = "ready";
        this.confirmOpen = true;
        this.$nextTick(() => this.$refs.confirmBtn?.focus());
      },

      reset() {
        clearTimeout(this.pollTimer);
        this.patientId = "";
        this.patientName = "";
        this.complaint = "";
        this.patient = "";
        this.doctor = "";
        this.metadata = "";
        this.showMeta = false;
        this.errors = {};
        this.banner = "";
        this.tx = null;
        this.hash = "";
        this.result = null;
        this.lastTokenId = null;
        this.phase = "idle";
      },
    }));
  });

  // Dipakai juga oleh halaman detail di fase 4.
  window.ehrTx = { ensureChain, postJSON, getJSON, shortHash, fmtNumber };
})();
