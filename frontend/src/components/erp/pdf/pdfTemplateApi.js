/**
 * pdf/pdfTemplateApi.js — pembungkus tipis API template PDF (SESI #19).
 *
 * Dipisah dari layarnya supaya satu tempat saja yang tahu bentuk URL & header
 * (dulu dua layar PDF memakai gaya berbeda: satu memakai `fetch('/api/...')`
 * relatif, satu memakai `${API}/api/...` — perbedaan sepele yang membuat salah
 * satu layar mati di lingkungan yang backend-nya beda origin).
 */
const API = process.env.REACT_APP_BACKEND_URL || '';

const jsonHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json',
});

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || 'Permintaan gagal');
  return data;
}

export const pdfTplApi = {
  catalog: (token) =>
    fetch(`${API}/api/pdf-templates/catalog`, { headers: jsonHeaders(token) }).then(handle),

  getGlobal: (token) =>
    fetch(`${API}/api/pdf-templates/global`, { headers: jsonHeaders(token) }).then(handle),

  saveGlobal: (token, body) =>
    fetch(`${API}/api/pdf-templates/global`, {
      method: 'PUT', headers: jsonHeaders(token), body: JSON.stringify(body),
    }).then(handle),

  getDoc: (token, docKey) =>
    fetch(`${API}/api/pdf-templates/${encodeURIComponent(docKey)}`, {
      headers: jsonHeaders(token),
    }).then(handle),

  saveDoc: (token, docKey, body) =>
    fetch(`${API}/api/pdf-templates/${encodeURIComponent(docKey)}`, {
      method: 'PUT', headers: jsonHeaders(token), body: JSON.stringify(body),
    }).then(handle),

  resetDoc: (token, docKey) =>
    fetch(`${API}/api/pdf-templates/${encodeURIComponent(docKey)}`, {
      method: 'DELETE', headers: jsonHeaders(token),
    }).then(handle),

  /** Pratinjau: PDF sungguhan (bukan tiruan HTML) → object URL untuk iframe. */
  previewUrl: async (token, docKey, template, format) => {
    const q = format === 'png' ? '?format=png' : '';
    const res = await fetch(`${API}/api/pdf-templates/preview${q}`, {
      method: 'POST',
      headers: jsonHeaders(token),
      body: JSON.stringify({ doc_key: docKey, template }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d?.detail || 'Pratinjau gagal dibuat');
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
};

export default pdfTplApi;
