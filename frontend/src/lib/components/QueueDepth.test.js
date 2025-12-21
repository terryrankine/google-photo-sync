import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import QueueDepth from './QueueDepth.svelte';

describe('QueueDepth', () => {
  const defaultQueue = {
    hash: { pending_batches: 0, running_batches: 0, pending_files: 0 },
    upload: { pending_batches: 0, running_batches: 0, pending_files: 0 }
  };

  describe('rendering', () => {
    it('renders hash and upload queue sections', () => {
      render(QueueDepth, { props: { queue: defaultQueue } });

      expect(screen.getByText('Hash Queue')).toBeInTheDocument();
      expect(screen.getByText('Upload Queue')).toBeInTheDocument();
    });

    it('shows running batches count', () => {
      const queue = {
        hash: { pending_batches: 5, running_batches: 2, pending_files: 100 },
        upload: { pending_batches: 3, running_batches: 1, pending_files: 50 }
      };
      render(QueueDepth, { props: { queue } });

      // Running batches are displayed as large numbers
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    it('shows pending batches text', () => {
      const queue = {
        hash: { pending_batches: 5, running_batches: 0, pending_files: 0 },
        upload: { pending_batches: 3, running_batches: 0, pending_files: 0 }
      };
      render(QueueDepth, { props: { queue } });

      expect(screen.getByText('5 pending')).toBeInTheDocument();
      expect(screen.getByText('3 pending')).toBeInTheDocument();
    });
  });

  describe('formatNumber', () => {
    it('shows file count for values under 1000', () => {
      const queue = {
        hash: { pending_batches: 1, running_batches: 0, pending_files: 500 },
        upload: { pending_batches: 0, running_batches: 0, pending_files: 0 }
      };
      render(QueueDepth, { props: { queue } });

      expect(screen.getByText('(500 files)')).toBeInTheDocument();
    });

    it('formats thousands with K suffix', () => {
      const queue = {
        hash: { pending_batches: 1, running_batches: 0, pending_files: 5000 },
        upload: { pending_batches: 0, running_batches: 0, pending_files: 0 }
      };
      render(QueueDepth, { props: { queue } });

      expect(screen.getByText('(5.0K files)')).toBeInTheDocument();
    });

    it('formats millions with M suffix', () => {
      const queue = {
        hash: { pending_batches: 1, running_batches: 0, pending_files: 2500000 },
        upload: { pending_batches: 0, running_batches: 0, pending_files: 0 }
      };
      render(QueueDepth, { props: { queue } });

      expect(screen.getByText('(2.5M files)')).toBeInTheDocument();
    });

    it('does not show file count when pending_files is 0', () => {
      const queue = {
        hash: { pending_batches: 1, running_batches: 0, pending_files: 0 },
        upload: { pending_batches: 1, running_batches: 0, pending_files: 0 }
      };
      const { container } = render(QueueDepth, { props: { queue } });

      expect(container.textContent).not.toContain('files)');
    });
  });

  describe('progress bar', () => {
    it('shows progress bar when batches are present', () => {
      const queue = {
        hash: { pending_batches: 5, running_batches: 5, pending_files: 0 },
        upload: { pending_batches: 0, running_batches: 0, pending_files: 0 }
      };
      const { container } = render(QueueDepth, { props: { queue } });

      // Progress bar should be 50% (5 running / 10 total)
      const progressBar = container.querySelector('.bg-green-500');
      expect(progressBar).toBeInTheDocument();
      expect(progressBar.style.width).toBe('50%');
    });

    it('does not show progress bar when no batches', () => {
      const { container } = render(QueueDepth, { props: { queue: defaultQueue } });

      // No colored progress bars should exist
      expect(container.querySelector('.bg-green-500')).not.toBeInTheDocument();
      expect(container.querySelector('.bg-blue-500')).not.toBeInTheDocument();
    });
  });
});
