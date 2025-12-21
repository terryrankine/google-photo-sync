import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import WorkerProgress from './WorkerProgress.svelte';

describe('WorkerProgress', () => {
  describe('rendering', () => {
    it('renders title', () => {
      render(WorkerProgress, { props: { workers: [], title: 'Hash Workers' } });

      expect(screen.getByText('Hash Workers')).toBeInTheDocument();
    });

    it('shows "No workers active" when empty', () => {
      render(WorkerProgress, { props: { workers: [] } });

      expect(screen.getByText('No workers active')).toBeInTheDocument();
    });

    it('renders worker list when workers exist', () => {
      const workers = [
        { worker_id: 1, idle: false, batch_number: 5, progress_percent: 50, files_processed: 25, files_total: 50, files_per_second: 10.5, throughput_mbps: 100 },
        { worker_id: 2, idle: true, batch_number: 0, progress_percent: 0, files_processed: 0, files_total: 0, files_per_second: 0, throughput_mbps: 0 }
      ];
      render(WorkerProgress, { props: { workers } });

      expect(screen.getByText('Worker 1')).toBeInTheDocument();
      expect(screen.getByText('Worker 2')).toBeInTheDocument();
    });
  });

  describe('worker status', () => {
    it('shows idle status for idle workers', () => {
      const workers = [{ worker_id: 1, idle: true }];
      render(WorkerProgress, { props: { workers } });

      expect(screen.getByText('Idle')).toBeInTheDocument();
    });

    it('shows batch number for active workers', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 42,
        progress_percent: 0, files_processed: 0, files_total: 100,
        files_per_second: 0, throughput_mbps: 0
      }];
      render(WorkerProgress, { props: { workers } });

      expect(screen.getByText('Batch #42')).toBeInTheDocument();
    });

    it('shows file progress for active workers', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 50, files_processed: 25, files_total: 50,
        files_per_second: 5.5, throughput_mbps: 50
      }];
      render(WorkerProgress, { props: { workers } });

      expect(screen.getByText('25/50 files')).toBeInTheDocument();
      expect(screen.getByText('5.5 files/s')).toBeInTheDocument();
    });
  });

  describe('speed formatting', () => {
    it('formats speed in KB/s for low throughput', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 50, files_processed: 25, files_total: 50,
        files_per_second: 5, throughput_mbps: 0.5
      }];
      render(WorkerProgress, { props: { workers } });

      expect(screen.getByText('512 KB/s')).toBeInTheDocument();
    });

    it('formats speed in MB/s for medium throughput', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 50, files_processed: 25, files_total: 50,
        files_per_second: 5, throughput_mbps: 150.5
      }];
      render(WorkerProgress, { props: { workers } });

      expect(screen.getByText('150.5 MB/s')).toBeInTheDocument();
    });

    it('formats speed in GB/s for high throughput', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 50, files_processed: 25, files_total: 50,
        files_per_second: 5, throughput_mbps: 1500
      }];
      render(WorkerProgress, { props: { workers } });

      expect(screen.getByText('1.5 GB/s')).toBeInTheDocument();
    });
  });

  describe('progress bar colors', () => {
    it('uses green for 75%+ progress', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 80, files_processed: 80, files_total: 100,
        files_per_second: 5, throughput_mbps: 100
      }];
      const { container } = render(WorkerProgress, { props: { workers } });

      expect(container.querySelector('.bg-green-500')).toBeInTheDocument();
    });

    it('uses blue for 50-74% progress', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 60, files_processed: 60, files_total: 100,
        files_per_second: 5, throughput_mbps: 100
      }];
      const { container } = render(WorkerProgress, { props: { workers } });

      expect(container.querySelector('.bg-blue-500')).toBeInTheDocument();
    });

    it('uses yellow for 25-49% progress', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 30, files_processed: 30, files_total: 100,
        files_per_second: 5, throughput_mbps: 100
      }];
      const { container } = render(WorkerProgress, { props: { workers } });

      expect(container.querySelector('.bg-yellow-500')).toBeInTheDocument();
    });

    it('uses gray for <25% progress', () => {
      const workers = [{
        worker_id: 1, idle: false, batch_number: 1,
        progress_percent: 10, files_processed: 10, files_total: 100,
        files_per_second: 5, throughput_mbps: 100
      }];
      const { container } = render(WorkerProgress, { props: { workers } });

      expect(container.querySelector('.bg-gray-500')).toBeInTheDocument();
    });
  });

  describe('totals display', () => {
    it('shows total throughput when provided', () => {
      render(WorkerProgress, {
        props: { workers: [], totalThroughput: 250, totalFilesPerSec: 15.5 }
      });

      expect(screen.getByText('250.0 MB/s')).toBeInTheDocument();
      expect(screen.getByText('15.5 files/s')).toBeInTheDocument();
    });

    it('hides throughput when zero', () => {
      const { container } = render(WorkerProgress, {
        props: { workers: [], totalThroughput: 0, totalFilesPerSec: 5.0 }
      });

      expect(container.textContent).not.toContain('MB/s');
      expect(screen.getByText('5.0 files/s')).toBeInTheDocument();
    });
  });
});
