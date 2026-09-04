// ESLint v9 FLAT CONFIG — DA37 ERP frontend
// ─────────────────────────────────────────────────────────────────────────────
// Kenapa file ini ada: repo tidak pernah meng-commit config ESLint, sedangkan
// devDependency `eslint@9` WAJIB punya `eslint.config.js` (flat config). Tanpa
// file ini setiap pemanggilan `npx eslint <file>` mati dengan
// "ESLint couldn't find an eslint.config.(js|mjs|cjs) file" → tooling lint
// (termasuk pre-commit / agent lint) tidak bisa jalan sama sekali.
//
// Filosofi rules: SAMA seperti CRA (`react-app`) — hanya menangkap ERROR nyata
// (variabel tak terdefinisi, hook dipakai salah, JSX rusak). Hal kosmetik
// (formatting, exhaustive-deps, unused vars) = WARNING supaya tidak memblokir
// build/CI yang sudah punya baseline 24 warning.
//
// CATATAN: build produksi TIDAK memakai ESLint (`DISABLE_ESLINT_PLUGIN=true` di
// frontend/.env) karena container preview terbatas CPU — lihat
// memory/PREVIEW_STABLE_MODE.md.
const js = require('@eslint/js');
const globals = require('globals');
const react = require('eslint-plugin-react');
const reactHooks = require('eslint-plugin-react-hooks');
const jsxA11y = require('eslint-plugin-jsx-a11y');

module.exports = [
  // 1) Yang TIDAK di-lint -----------------------------------------------------
  {
    ignores: [
      'build/**',
      'dist/**',
      'coverage/**',
      'node_modules/**',
      'public/**',
      'plugins/**',
      'static_server.js',
      '**/*.min.js',
      // Kode ARSIP: tidak di-import komponen aktif mana pun (hanya disebut di
      // komentar moduleRegistry) & tidak masuk bundle. Melint-nya hanya
      // menghasilkan error semu dari API lama yang sudah tidak dipakai.
      'src/components/erp/_archive/**',
    ],
  },

  // 2) Basis rekomendasi ESLint untuk semua source ----------------------------
  js.configs.recommended,

  // 3) Source aplikasi (browser + JSX) ---------------------------------------
  {
    files: ['src/**/*.{js,jsx,mjs}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.es2021,
        process: 'readonly',
        jest: 'readonly',
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
    settings: {
      react: { version: 'detect' },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'jsx-a11y': jsxA11y,
    },
    rules: {
      // ── ERROR: bug nyata ───────────────────────────────────────────────────
      'react/jsx-uses-vars': 'error', // komponen dipakai di JSX ≠ unused
      'react/jsx-uses-react': 'off', // React 17+ automatic runtime
      'react/react-in-jsx-scope': 'off',
      'react/jsx-no-undef': 'error', // <Foo/> tanpa import → runtime crash
      'react/jsx-key': 'error',
      'react/no-children-prop': 'error',
      'react-hooks/rules-of-hooks': 'error', // hook di dalam if/loop → crash
      'no-undef': 'error', // ReferenceError (mis. useMemo lupa di-import)
      'no-dupe-keys': 'error',
      'no-dupe-class-members': 'error',
      'no-unreachable': 'error',
      'no-cond-assign': 'error',
      'no-const-assign': 'error',
      'no-obj-calls': 'error',
      'no-sparse-arrays': 'error',
      'valid-typeof': 'error',
      'use-isnan': 'error',

      // ── WARNING: kosmetik / baseline lama ─────────────────────────────────
      'react-hooks/exhaustive-deps': 'warn',
      'no-unused-vars': ['warn', {
        args: 'none',
        ignoreRestSiblings: true,
        varsIgnorePattern: '^_',
        argsIgnorePattern: '^_',
      }],
      'no-empty': ['warn', { allowEmptyCatch: true }],
      'no-useless-escape': 'warn',
      'no-prototype-builtins': 'off',
      'no-control-regex': 'off',
      'react/prop-types': 'off', // proyek tidak pakai PropTypes
      'react/display-name': 'off',
      'react/no-unescaped-entities': 'off', // teks Bahasa Indonesia pakai ' dan "
      'jsx-a11y/alt-text': 'warn',
      'jsx-a11y/anchor-is-valid': 'warn',
    },
  },

  // 4) File setup TEST (jest/node globals) -----------------------------------
  // `src/setupTests.js` memakai `global.*` (API Node) → dengan globals browser
  // saja ia dilaporkan `no-undef` (6 error) padahal wajar untuk file setup Jest.
  {
    files: ['src/setupTests.js', 'src/**/*.test.{js,jsx}', 'src/**/__tests__/**/*.{js,jsx}'],
    languageOptions: {
      globals: { ...globals.node, ...globals.jest },
    },
  },

  // 5) File config/tooling Node (CommonJS) -----------------------------------
  {
    files: [
      '*.js',
      'craco.config.js',
      'tailwind.config.js',
      'postcss.config.js',
      'eslint.config.js',
      'scripts/**/*.js',
    ],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: { ...globals.node },
    },
    rules: {
      'no-unused-vars': 'warn',
    },
  },
];
