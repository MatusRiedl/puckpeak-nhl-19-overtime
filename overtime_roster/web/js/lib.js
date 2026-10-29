// React 18 (vendor/, MIT) + htm (vendor/, Apache-2.0): JSX-like templates with no build step.
import htm from '../vendor/htm.module.js';

const R = window.React;
export const html = htm.bind(R.createElement);
export const {
  useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback, useReducer, useSyncExternalStore, Fragment, memo,
} = R;
export const { createPortal } = window.ReactDOM;

export const cls = (...parts) => parts.filter(Boolean).join(' ');
