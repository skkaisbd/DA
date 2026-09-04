/**
 * lazyWithRetry.js — Chunk-loading retry helper
 * Sprint Pre-Dev Health Check (2026-05-26) — mitigates RC-2 from Aurora F&B bug report.
 *
 * Problem: When a lazy-loaded chunk fails to fetch (network blip, CDN miss,
 * slow ingress latency), React's chunk loader CACHES the rejected promise.
 * Every subsequent navigation throws the same rejection → permanent blank.
 * Hard refresh fixes it because the chunk-loader cache is cleared.
 *
 * Solution:
 * 1. Retry the import() up to 3× with exponential backoff before failing.
 * 2. If all retries fail, resolve to a graceful fallback component instead
 *    of a rejected promise (so React doesn't cache a failure permanently).
 */

const MAX_RETRIES = 3;
const BASE_DELAY_MS = 500;

/**
 * Wrap a dynamic import() with retry + fallback.
 *
 * @param {() => Promise<{default: Component}>} importFn
 * @param {string} [displayName] - For debugging / error display
 * @returns React.lazy-compatible promise factory
 */
export function lazyWithRetry(importFn, displayName = 'Module') {
  return () =>
    new Promise((resolve) => {
      let attempt = 0;

      const tryLoad = () => {
        importFn()
          .then(resolve)
          .catch((err) => {
            attempt += 1;
            if (attempt < MAX_RETRIES) {
              const delay = BASE_DELAY_MS * Math.pow(2, attempt - 1); // 500, 1000, 2000ms
              console.warn(
                `[lazyWithRetry] ${displayName} chunk load failed (attempt ${attempt}/${MAX_RETRIES}), retry in ${delay}ms.`,
                err?.message || err,
              );
              setTimeout(tryLoad, delay);
            } else {
              // All retries exhausted — resolve with fallback component so
              // React does NOT cache a rejected promise (which would require
              // a hard refresh to clear).
              console.error(
                `[lazyWithRetry] ${displayName} failed to load after ${MAX_RETRIES} attempts.`,
                err?.message || err,
              );
              resolve({
                default: ChunkLoadErrorFallback(displayName),
              });
            }
          });
      };

      tryLoad();
    });
}

/**
 * Friendly fallback rendered when a chunk fails to load even after retries.
 */
function ChunkLoadErrorFallback(name) {
  return function ChunkError() {
    return (
      <div
        className="min-h-screen grid place-items-center bg-background"
        role="alert"
        aria-label={`${name} gagal dimuat`}
      >
        <div className="flex flex-col items-center gap-4 max-w-sm text-center p-6">
          <div className="w-12 h-12 rounded-full bg-amber-400/15 border border-amber-300/25 flex items-center justify-center text-amber-400 text-2xl">
            ⚠️
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">Gagal Memuat Halaman</p>
            <p className="text-xs text-muted-foreground mt-1">
              Koneksi bermasalah saat memuat <em>{name}</em>. Coba{' '}
              <button
                type="button"
                className="underline text-[hsl(var(--primary))] font-medium"
                onClick={() => window.location.reload()}
              >
                refresh halaman
              </button>
              .
            </p>
          </div>
        </div>
      </div>
    );
  };
}
