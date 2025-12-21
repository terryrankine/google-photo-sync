import { writable } from 'svelte/store';
import { api } from '../api.js';

// Cached jobs data
export const jobs = writable([]);
export const activeJob = writable(null);
export const jobsLoaded = writable(false);

// Load jobs list
export async function loadJobs(limit = 20) {
  try {
    const data = await api.getJobs(limit);
    jobs.set(data);
    jobsLoaded.set(true);
    return data;
  } catch (e) {
    console.error('Failed to load jobs:', e);
    return [];
  }
}

// Load active job
export async function loadActiveJob() {
  try {
    const data = await api.getActiveJob();
    activeJob.set(data);
    return data;
  } catch (e) {
    console.error('Failed to load active job:', e);
    return null;
  }
}

// Refresh jobs
export async function refreshJobs() {
  return loadJobs();
}
