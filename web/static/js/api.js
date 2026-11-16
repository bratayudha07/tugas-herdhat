/*
 * Pembungkus fetch kecil untuk API internal.
 *
 * Semua endpoint mengembalikan JSON, termasuk saat error (`{error, fields}`),
 * jadi pemanggil tidak perlu menebak bentuk respons. Didaftarkan sebelum
 * `tx.js` dan `account.js` supaya keduanya memakai helper yang sama.
 */
(() => {
  async function readJSON(response) {
    try {
      return (await response.json()) || {};
    } catch (error) {
      // Bukan JSON (mis. halaman HTML error) — anggap kosong.
      return {};
    }
  }

  async function getJSON(url) {
    const response = await fetch(url);
    return { ok: response.ok, status: response.status, data: await readJSON(response) };
  }

  async function postJSON(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return { ok: response.ok, status: response.status, data: await readJSON(response) };
  }

  window.ehrApi = { getJSON, postJSON };
})();
