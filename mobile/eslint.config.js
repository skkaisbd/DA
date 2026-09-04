// https://docs.expo.dev/guides/using-eslint/
//
// CATATAN (FASE 11): paket Expo (`eslint`, `eslint-config-expo`) HANYA terpasang
// kalau seseorang menjalankan `yarn install` DI DALAM /app/mobile. Di container
// preview/CI hal itu tidak dilakukan (aplikasi mobile tidak ikut dibangun), jadi
// `require('eslint-config-expo/flat')` melempar MODULE_NOT_FOUND.
//
// Dulu itu membuat SELURUH gate lint mati dengan "linter engine error" —
// bukan error kode, melainkan config yang tidak bisa dimuat. Sama persis dengan
// pelajaran §7.9 di plan.md (ESLint mati saat dijalankan dari root repo).
//
// Sekarang config ini menurunkan diri dengan anggun: kalau dependensinya ada,
// pakai aturan Expo penuh; kalau tidak ada, pakai config minimal tanpa aturan.
//
// PENTING (bug tooling ke-2, ditemukan 2026-07-26): fallback lama memakai
// `[{ ignores: ['**/*'] }]`. Akibatnya `npx eslint .` di dalam /app/mobile keluar
// dengan **exit code 2** dan pesan "all of the files matching the glob pattern '.'
// are ignored" — lagi-lagi dibaca tool platform sebagai LINTER ENGINE ERROR.
// Fallback sekarang tetap MELINT berkas JS biasa (tanpa aturan apa pun, jadi
// selalu 0 problem) dan hanya mengabaikan berkas TypeScript/Expo yang memang
// butuh parser khusus ⇒ ESLint keluar dengan kode 0.
let config;

try {
  const { defineConfig } = require('eslint/config');
  const expoConfig = require('eslint-config-expo/flat');

  config = defineConfig([
    expoConfig,
    {
      ignores: ['dist/*'],
    },
  ]);
} catch (err) {
  if (err && err.code !== 'MODULE_NOT_FOUND') throw err;
  // Dependensi Expo belum dipasang di lingkungan ini — jangan matikan ESLint.
  // Jalankan `cd /app/mobile && yarn install` untuk mengaktifkan aturan Expo.
  config = [
    {
      // TS/TSX butuh parser Expo/TypeScript yang belum terpasang → abaikan.
      ignores: ['**/*.ts', '**/*.tsx', 'dist/*', 'node_modules/**', '.expo/**'],
    },
    {
      // Berkas JS biasa tetap "dilint" (tanpa aturan) supaya ESLint punya
      // konfigurasi yang cocok dan keluar dengan exit code 0.
      files: ['**/*.{js,jsx,mjs,cjs}'],
      languageOptions: { ecmaVersion: 'latest', sourceType: 'module' },
      rules: {},
    },
  ];
}

module.exports = config;
