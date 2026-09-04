// Jest + React Testing Library setup
import '@testing-library/jest-dom';

// Polyfill TextEncoder/TextDecoder for some libraries
import { TextEncoder, TextDecoder } from 'util';
if (typeof global.TextEncoder === 'undefined') global.TextEncoder = TextEncoder;
if (typeof global.TextDecoder === 'undefined') global.TextDecoder = TextDecoder;

// Polyfill ResizeObserver (used by ResponsiveTableWrapper)
if (typeof global.ResizeObserver === 'undefined') {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Polyfill matchMedia for components that detect viewport size
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Suppress noisy console.warn during tests (Radix dev warnings, etc.)
const originalWarn = console.warn;
console.warn = (...args) => {
  const msg = String(args[0] || '');
  if (msg.includes('not wrapped in act')) return; // jsdom flakiness
  if (msg.includes('Missing `Description`')) return; // we test for this elsewhere
  originalWarn(...args);
};
