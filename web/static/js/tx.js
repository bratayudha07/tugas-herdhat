/*
 * Mesin transaksi di browser: validasi server → konfirmasi → MetaMask →
 * pantau receipt.
 *
 * Server hanya menyiapkan `to` + `data`; tanda tangan terjadi di wallet.
 * Private key tidak pernah dikirim ke server maupun disimpan di file ini.
 *
 * `txMachine()` dipakai dua halaman (Buat Batch & Detail) supaya alur status
 * tidak ditulis dua kali. Komponen halaman tinggal menempel field-nya sendiri
 * lewat `Object.assign(txMachine(), {...})`.
 */
(() => {
  const POLL_INTERVAL = 2000;
  const POLL_TIMEOUT = 60000;

  const wallet = () => Alpine.store("wallet");

  // Helper fetch dipakai bersama `account.js`; dimuat dari `api.js`.
  const { getJSON, postJSON } = window.ehrApi;

  function shortHash(hash) {
    if (!hash) return "";
    return `${hash.slice(0, 10)}…${hash.slice(-6)}`;
  }

  function fmtNumber(value) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString("id-ID");
  }

  /**
   * Catat transaksi yang sudah sampai ke node ke riwayat sesi (localStorage).
   *
   * Yang dicatat hanya yang punya hash — penolakan MetaMask tidak pernah
   * menghasilkan hash, jadi tidak ada yang bisa ditampilkan di halaman Wallet.
   */
  function recordSession(state) {
    if (!this.hash) return;
    window.ehrSession?.add({
      hash: this.hash,
      state,
      action: this.tx?.action || "",
      label: this.tx?.label || "Transaksi",
      block: this.result?.block ?? null,
      gas: this.result?.gas ?? null,
      tokenId: this.result?.tokenId ?? this.tx?.predictedTokenId ?? null,
      from: this.tx?.from || wallet().address,
      reason: this.result?.reason || "",
    });
  }

  /**
   * State & aksi transaksi yang dipakai bersama.
   *
   * `prepare()` hanya meminta calldata ke server (validasi + dry-run);
   * `send()` menyerahkan `to` + `data` ke wallet. Halaman yang memakai mesin
   * ini wajib punya `x-ref="summary"` (ringkasan error) dan `x-ref="panel"`
   * (kartu status) supaya fokus/scroll bisa diarahkan.
   */
  function txMachine() {
    return {
      phase: "idle", // idle | building | ready | signing | pending | success | failed | rejected | timeout | error | invalid
      errors: {},
      banner: "",
      tx: null,
      hash: "",
      result: null,
      confirmOpen: false,
      pollTimer: null,
      startedAt: 0,

      // --- turunan ----------------------------------------------------

      busy() {
        return ["building", "signing", "pending"].includes(this.phase);
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
            return "Belum dikonfirmasi setelah 60 detik. Cek data di halaman — kalau sudah masuk, isinya berubah.";
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

      revealPanel() {
        this.$nextTick(() =>
          this.$refs.panel?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
        );
      },

      // --- alur -------------------------------------------------------

      /**
       * Minta server memvalidasi & menyiapkan calldata, lalu buka dialog.
       * Mengembalikan `true` kalau dialog konfirmasi terbuka.
       */
      async prepare(action, args = {}) {
        if (this.busy()) return false;

        this.errors = {};
        this.banner = "";
        this.result = null;
        this.hash = "";
        this.phase = "building";

        const response = await postJSON("/api/tx/build", {
          action,
          from: wallet().address,
          args,
        });

        if (!response.ok) {
          this.phase = "invalid";
          this.errors = response.data.fields || {};
          this.banner = response.data.error || "Gagal menyiapkan transaksi.";
          this.$nextTick(() => this.$refs.summary?.focus());
          return false;
        }

        this.tx = response.data;
        this.phase = "ready";
        this.confirmOpen = true;
        this.$nextTick(() => this.$refs.confirmBtn?.focus());
        return true;
      },

      closeConfirm() {
        this.confirmOpen = false;
        this.phase = this.tx ? "ready" : "idle";
        this.$nextTick(() => this.$refs.submitBtn?.focus());
      },

      async send() {
        if (!this.tx) return;
        this.confirmOpen = false;
        this.phase = "signing";
        this.banner = "";

        try {
          await wallet().ensureChain();
        } catch (error) {
          this.phase = "error";
          this.banner =
            "Jaringan wallet tidak cocok dengan RPC. Ganti jaringan di MetaMask, lalu ulangi.";
          this.revealPanel();
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
        const success = response.data.state === "success";
        try {
          // Refresh konteks dulu, baru tandai sukses: begitu panel bilang
          // "berhasil", tombol di kartu aksi sudah sesuai state chain.
          if (success) await this.onTxSuccess(this.result);
        } finally {
          this.phase = success ? "success" : "failed";
        }
        recordSession.call(this, this.phase);
        this.revealPanel();
      },

      /** Kait halaman: dipanggil sekali setelah transaksi sukses masuk blok. */
      async onTxSuccess() {},

      /** Muat ulang halaman penuh — dipakai panel sukses di beberapa halaman. */
      refreshPage() {
        window.location.reload();
      },

      // Kirim ulang transaksi yang sudah disiapkan (mis. setelah user menolak
      // di MetaMask) — tidak perlu validasi ulang, calldata masih sama.
      retry() {
        if (!this.tx) {
          this.clearTx();
          return;
        }
        this.banner = "";
        this.phase = "ready";
        this.confirmOpen = true;
        this.$nextTick(() => this.$refs.confirmBtn?.focus());
      },

      clearTx() {
        clearTimeout(this.pollTimer);
        this.tx = null;
        this.hash = "";
        this.result = null;
        this.errors = {};
        this.banner = "";
        this.confirmOpen = false;
        this.phase = "idle";
      },
    };
  }

  document.addEventListener("alpine:init", () => {
    Alpine.data("createBatchForm", () =>
      Object.assign(txMachine(), {
        // isi form
        patientId: "",
        patientName: "",
        complaint: "",
        patient: "",
        doctor: "",
        metadata: "",
        showMeta: false,

        role: null,
        roleLoading: false,
        lastTokenId: null,

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
          this.clearTx();
        },

        // --- data turunan ---------------------------------------------

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

        complaintLeft() {
          return 280 - this.complaint.length;
        },

        // --- peran ----------------------------------------------------

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

        // --- alur -----------------------------------------------------

        submit() {
          if (this.gate() !== "open" || this.busy()) return;

          this.lastTokenId = null;
          return this.prepare("createBatch", {
            patientId: this.patientId,
            patientName: this.patientName,
            complaint: this.complaint,
            patient: this.patient,
            doctor: this.doctor,
            metadata: this.showMeta ? this.metadata : "",
          });
        },

        async onTxSuccess(result) {
          this.lastTokenId = result.tokenId;
        },

        reset() {
          this.clearTx();
          this.patientId = "";
          this.patientName = "";
          this.complaint = "";
          this.patient = "";
          this.doctor = "";
          this.metadata = "";
          this.showMeta = false;
          this.lastTokenId = null;
        },
      }),
    );

    /**
     * Aksi tulis di halaman detail.
     *
     * Hak tulis tidak ditebak dari data yang sudah dirender: setiap kali akun
     * berganti (atau setelah transaksi sukses) status otorisasi dibaca ulang
     * dari `/api/batch/{id}/context`, sehingga tombol yang tampil selalu
     * sesuai state chain.
     */
    Alpine.data("batchActions", () =>
      Object.assign(txMachine(), {
        tokenId: 0,
        treatment: "",
        medicine: "",
        doctor: "",

        ctx: null,
        ctxError: "",
        loading: false,

        init() {
          const el = this.$el;
          this.tokenId = Number(el.dataset.tokenId || 0);
          this.treatment = el.dataset.treatment || "";
          this.medicine = el.dataset.medicine || "";

          this.$watch(
            () => wallet().address,
            () => this.loadContext(),
          );
          this.loadContext();
        },

        destroy() {
          this.clearTx();
        },

        // --- konteks otorisasi ----------------------------------------

        async loadContext() {
          if (!wallet().address) {
            this.ctx = null;
            this.ctxError = "";
            return;
          }

          this.loading = true;
          try {
            const response = await getJSON(
              `/api/batch/${this.tokenId}/context?address=${encodeURIComponent(
                wallet().address,
              )}`,
            );
            if (response.ok) {
              this.ctx = response.data;
              this.ctxError = "";
            } else {
              this.ctx = null;
              this.ctxError =
                response.data.error || "Gagal membaca hak akses batch ini.";
            }
          } finally {
            this.loading = false;
          }
        },

        mode() {
          if (!wallet().hasProvider) return "no-provider";
          if (!wallet().address) return "no-wallet";
          if (this.ctxError) return "error";
          if (this.loading && !this.ctx) return "checking";
          if (!this.ctx) return "checking";
          if (this.ctx.completed) return "completed";
          if (this.ctx.role === "DOCTOR") return "doctor";
          if (this.ctx.role === "PATIENT") return "patient";
          if (this.ctx.role === "RECEPTIONIST") return "receptionist";
          return "viewer";
        },

        short(addr) {
          if (!addr) return "—";
          return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
        },

        treatmentLeft() {
          return 280 - this.treatment.length;
        },

        medicineLeft() {
          return 280 - this.medicine.length;
        },

        // --- aksi -----------------------------------------------------

        advance() {
          return this.prepare("updateStatus", { tokenId: this.tokenId });
        },

        saveTreatment() {
          return this.prepare("updateTreatment", {
            tokenId: this.tokenId,
            treatment: this.treatment,
            medicine: this.medicine,
          });
        },

        setConsent(granted) {
          return this.prepare("setConsent", {
            tokenId: this.tokenId,
            granted: Boolean(granted),
          });
        },

        assignDoctor() {
          return this.prepare("assignDoctor", {
            tokenId: this.tokenId,
            doctor: this.doctor,
          });
        },

        async onTxSuccess() {
          // Server sudah membuang cache bacaan setelah receipt sukses, jadi
          // konteks baru di sini mencerminkan status/izin setelah transaksi.
          await this.loadContext();
        },
      }),
    );
  });

  // Helper kecil yang mungkin dipakai halaman lain. Fetch & wallet ada di
  // `window.ehrApi` dan `Alpine.store("wallet")`.
  window.ehrTx = { shortHash, fmtNumber, txMachine };
})();
