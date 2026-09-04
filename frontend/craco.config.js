// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build, not tests)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build,
// NODE_ENV=test for jest. Visual edits would interfere with text-content tests.
const isDevServer = process.env.NODE_ENV !== "production" && process.env.NODE_ENV !== "test";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  jest: {
    configure: (jestConfig) => {
      jestConfig.moduleNameMapper = {
        ...jestConfig.moduleNameMapper,
        // Path alias for `@/...` → `src/...` (matches webpack alias above)
        '^@/(.*)$': '<rootDir>/src/$1',
      };
      // Ignore helper files (prefixed `_`) inside __tests__ — they're shared
      // utils (e.g. `_test-utils.jsx`), not test suites themselves.
      jestConfig.testPathIgnorePatterns = [
        ...(jestConfig.testPathIgnorePatterns || []),
        '<rootDir>/src/__tests__/_',
      ];
      return jestConfig;
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // ── FIX (react-data-grid beta "ecij" bug) ───────────────────────────
      // react-data-grid 7.0.0-beta.* ships a broken side-effect import on
      // line 3 of lib/index.js: `import "ecij";`. `ecij` is an unresolvable
      // bundler artifact — the package has ZERO dependencies and no `ecij`
      // module exists, so webpack fails with:
      //   Module not found: Can't resolve 'ecij' in react-data-grid/lib
      // Nothing is imported FROM it (side-effect only), so we alias it to an
      // empty module (webpack 5 treats alias value `false` as empty module).
      // Grid styles are imported separately via 'react-data-grid/lib/styles.css'.
      webpackConfig.resolve = webpackConfig.resolve || {};
      webpackConfig.resolve.alias = {
        ...(webpackConfig.resolve.alias || {}),
        ecij: false,
      };

      // ── Constrained-container build tuning (1 CPU core / 2GB RAM) ────────
      // Terser JS minification is the single heaviest step of `yarn build`.
      // On a 1-core container it can take very long and risk OOM. We disable
      // minification for production builds so the one-time build finishes
      // reliably. Bundle is larger (uncompressed) but 100% functional — it is
      // served locally by `serve`, so download size is irrelevant here.
      if (process.env.NODE_ENV === "production") {
        webpackConfig.optimization = webpackConfig.optimization || {};
        webpackConfig.optimization.minimize = false;
      }

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Session #11.17: Suppress source-map warnings from html5-qrcode library.
      // html5-qrcode ships ESM files with .map references to non-existent /src/*.ts files,
      // causing 23 warnings per compile. Excluding it from source-map-loader resolves them
      // without affecting our own source maps. See: https://github.com/mebjas/html5-qrcode/issues/566
      if (webpackConfig.module && Array.isArray(webpackConfig.module.rules)) {
        webpackConfig.module.rules.forEach((rule) => {
          if (!rule) return;
          // Pattern A: top-level rule with `loader: 'source-map-loader'` and `enforce: 'pre'`
          const isTopLevelSourceMap =
            typeof rule.loader === 'string' && rule.loader.includes('source-map-loader');
          // Pattern B: `use: [{ loader: 'source-map-loader' }, ...]`
          const usesArr = Array.isArray(rule.use) ? rule.use : (rule.use ? [rule.use] : []);
          const isUseSourceMap = usesArr.some(
            (u) => typeof u === 'object' && u && u.loader && u.loader.includes('source-map-loader')
          );
          if (isTopLevelSourceMap || isUseSourceMap) {
            const excludeAddition = /node_modules[\\/]html5-qrcode/;
            if (rule.exclude) {
              rule.exclude = Array.isArray(rule.exclude)
                ? [...rule.exclude, excludeAddition]
                : [rule.exclude, excludeAddition];
            } else {
              rule.exclude = [excludeAddition];
            }
          }
          // Pattern C: rule.oneOf entries
          if (Array.isArray(rule.oneOf)) {
            rule.oneOf.forEach((subRule) => {
              if (!subRule) return;
              const subUses = Array.isArray(subRule.use) ? subRule.use : (subRule.use ? [subRule.use] : []);
              const subIsSourceMap =
                (typeof subRule.loader === 'string' && subRule.loader.includes('source-map-loader')) ||
                subUses.some((u) => typeof u === 'object' && u && u.loader && u.loader.includes('source-map-loader'));
              if (subIsSourceMap) {
                const excludeAddition = /node_modules[\\/]html5-qrcode/;
                if (subRule.exclude) {
                  subRule.exclude = Array.isArray(subRule.exclude)
                    ? [...subRule.exclude, excludeAddition]
                    : [subRule.exclude, excludeAddition];
                } else {
                  subRule.exclude = [excludeAddition];
                }
              }
            });
          }
        });
      }

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

module.exports = webpackConfig;
