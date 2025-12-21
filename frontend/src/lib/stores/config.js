import { writable } from 'svelte/store';
import { api } from '../api.js';

// Cached config data
export const config = writable({
  source_dirs: '[]',
  file_extensions: '.jpg,.jpeg,.png,.heic,.mp4,.mov',
  ignore_patterns: '.thumbnails,@eaDir',
  parallel_uploads: 4,
  parallel_hashers: 4
});
export const authStatus = writable(null);
export const configLoaded = writable(false);

// Load config
export async function loadConfig() {
  try {
    const data = await api.getConfig();
    config.set(data);
    configLoaded.set(true);
    return data;
  } catch (e) {
    console.error('Failed to load config:', e);
    return null;
  }
}

// Load auth status
export async function loadAuthStatus() {
  try {
    const data = await api.getAuthStatus();
    authStatus.set(data);
    return data;
  } catch (e) {
    console.error('Failed to load auth status:', e);
    return null;
  }
}

// Load all config data
export async function loadAllConfig() {
  try {
    const [configData, auth] = await Promise.all([
      api.getConfig(),
      api.getAuthStatus()
    ]);
    config.set(configData);
    authStatus.set(auth);
    configLoaded.set(true);
  } catch (e) {
    console.error('Failed to load config:', e);
  }
}
