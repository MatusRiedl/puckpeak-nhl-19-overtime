// The page's copy of Python's state. Python sends whole slices ({meta, slices, log, events}); components read a
// slice with useSlice(name) and redraw when it changes.
import { useSyncExternalStore } from './lib.js';

const state = { meta: {}, slices: {}, log: [] };
const listeners = new Set();
const eventHandlers = new Map();
let version = 0;

function notify() {
  version += 1;
  listeners.forEach((fn) => fn());
}

export function receive(message) {
  if (!message || typeof message !== 'object') return;
  if (message.meta) state.meta = message.meta;
  if (message.slices) state.slices = { ...state.slices, ...message.slices };
  if (message.log) {
    state.log = message.log.clear ? message.log.lines.slice() : state.log.concat(message.log.lines);
    if (state.log.length > 5000) state.log = state.log.slice(-5000);
  }
  notify();
  (message.events || []).forEach(([name, payload]) => (eventHandlers.get(name) || []).forEach((fn) => fn(payload)));
}

export function onEvent(name, fn) {
  if (!eventHandlers.has(name)) eventHandlers.set(name, []);
  eventHandlers.get(name).push(fn);
}

function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useSlice(name) {
  return useSyncExternalStore(subscribe, () => state.slices[name]);
}

export function useLog() {
  return useSyncExternalStore(subscribe, () => state.log);
}

export function useMeta() {
  return useSyncExternalStore(subscribe, () => state.meta);
}

window.OT = { receive, state };
