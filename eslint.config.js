// ESLint FLAT CONFIG di ROOT REPO (/app/eslint.config.js)
// ─────────────────────────────────────────────────────────────────────────────
// KENAPA FILE INI ADA (bug tooling nyata, ditemukan 2026-07-25):
// `frontend/eslint.config.js` hanya berlaku kalau ESLint dijalankan DARI dalam
// `frontend/`. Kalau dijalankan dari ROOT repo (yang dilakukan gate/CI dan
// beberapa tool otomatis), ESLint v9 mati total dengan:
//     "ESLint couldn't find an eslint.config.(js|mjs|cjs) file."
// Itu bukan "lint error" melainkan LINTER ENGINE ERROR — jadi seluruh gate lint
// gagal tanpa pernah benar-benar memeriksa kode. File ini menutup celah itu.
//
// PRINSIP: JANGAN duplikasi aturan. Kita MUAT config frontend lalu geser
// (rebase) semua glob `files`/`ignores` dengan awalan `frontend/` supaya
// perilakunya identik saat dijalankan dari root.
// Catatan resolusi modul: `require('./frontend/eslint.config.js')` membuat
// require di DALAM file itu (`@eslint/js`, `globals`, plugin react, dst.)
// di-resolve relatif terhadap `frontend/` ⇒ memakai `frontend/node_modules`.
// Jadi root repo TIDAK perlu punya node_modules sendiri.
const frontendConfigs = require('./frontend/eslint.config.js');

const PREFIX = 'frontend/';

// Glob yang sudah "global" (mis. `**/*.min.js`) atau sudah berawalan frontend/
// dibiarkan; sisanya digeser ke dalam folder frontend.
function rebase(glob) {
  if (typeof glob !== 'string') return glob;
  if (glob.startsWith('**/')) return glob;
  if (glob.startsWith(PREFIX)) return glob;
  return PREFIX + glob;
}

module.exports = [
  // 1) Yang TIDAK di-lint dari root ------------------------------------------
  {
    ignores: [
      '**/node_modules/**',
      'frontend/build/**',
      'frontend/public/**',
      // Webpack plugin lokal (Node, bukan kode aplikasi)
      'frontend/plugins/**',
      'frontend/static_server.js',
      // Aplikasi mobile React Native/Expo punya `mobile/eslint.config.js`
      // sendiri (preset expo). Melintnya dari sini akan salah aturan.
      'mobile/**',
      // Artefak & aset, bukan source
      'uploads/**',
      'refs/**',
      'backups/**',
      'docs/**',
      '**/*.min.js',
      // Kode arsip: tidak di-import komponen aktif & tidak masuk bundle
      'frontend/src/components/erp/_archive/**',
    ],
  },

  // 2) Aturan frontend, glob digeser ke `frontend/…` --------------------------
  ...frontendConfigs.map((cfg) => {
    const out = { ...cfg };
    if (Array.isArray(cfg.files)) out.files = cfg.files.map(rebase);
    if (Array.isArray(cfg.ignores)) out.ignores = cfg.ignores.map(rebase);
    return out;
  }),

  // 3) File config Node (CommonJS) di ROOT repo -------------------------------
  // Termasuk file ini sendiri. Tanpa blok ini `require`/`module` dilaporkan
  // `no-undef` karena blok Node di config frontend sudah digeser ke `frontend/*.js`.
  // Globals ditulis manual (bukan paket `globals`) supaya root tidak bergantung
  // pada path node_modules frontend.
  {
    files: ['*.js', '*.cjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        require: 'readonly',
        module: 'writable',
        exports: 'writable',
        __dirname: 'readonly',
        __filename: 'readonly',
        process: 'readonly',
        console: 'readonly',
        Buffer: 'readonly',
      },
    },
    rules: { 'no-unused-vars': 'warn' },
  },
];
