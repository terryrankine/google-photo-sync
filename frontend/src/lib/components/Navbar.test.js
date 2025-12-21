import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';

// Mock svelte-routing
vi.mock('svelte-routing', () => ({
  link: () => {} // Return a no-op action
}));

import Navbar from './Navbar.svelte';

describe('Navbar', () => {
  describe('branding', () => {
    it('renders app name', () => {
      render(Navbar, { props: { status: 'idle' } });

      expect(screen.getByText('GPhoto Sync')).toBeInTheDocument();
    });
  });

  describe('navigation links', () => {
    it('renders all navigation links', () => {
      render(Navbar, { props: { status: 'idle' } });

      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Jobs')).toBeInTheDocument();
      expect(screen.getByText('Statistics')).toBeInTheDocument();
      expect(screen.getByText('Files')).toBeInTheDocument();
      expect(screen.getByText('Logs')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });

    it('has correct href for Dashboard link', () => {
      render(Navbar, { props: { status: 'idle' } });

      const dashboardLink = screen.getByText('Dashboard').closest('a');
      expect(dashboardLink).toHaveAttribute('href', '/');
    });

    it('has correct href for Jobs link', () => {
      render(Navbar, { props: { status: 'idle' } });

      const jobsLink = screen.getByText('Jobs').closest('a');
      expect(jobsLink).toHaveAttribute('href', '/jobs');
    });

    it('has correct href for Statistics link', () => {
      render(Navbar, { props: { status: 'idle' } });

      const statsLink = screen.getByText('Statistics').closest('a');
      expect(statsLink).toHaveAttribute('href', '/stats');
    });

    it('has correct href for Files link', () => {
      render(Navbar, { props: { status: 'idle' } });

      const filesLink = screen.getByText('Files').closest('a');
      expect(filesLink).toHaveAttribute('href', '/files');
    });

    it('has correct href for Logs link', () => {
      render(Navbar, { props: { status: 'idle' } });

      const logsLink = screen.getByText('Logs').closest('a');
      expect(logsLink).toHaveAttribute('href', '/logs');
    });

    it('has correct href for Settings link', () => {
      render(Navbar, { props: { status: 'idle' } });

      const settingsLink = screen.getByText('Settings').closest('a');
      expect(settingsLink).toHaveAttribute('href', '/config');
    });
  });

  describe('status indicator', () => {
    it('shows idle status', () => {
      render(Navbar, { props: { status: 'idle' } });

      expect(screen.getByText('idle')).toBeInTheDocument();
    });

    it('shows running status', () => {
      render(Navbar, { props: { status: 'running' } });

      expect(screen.getByText('running')).toBeInTheDocument();
    });

    it('shows paused status', () => {
      render(Navbar, { props: { status: 'paused' } });

      expect(screen.getByText('paused')).toBeInTheDocument();
    });

    it('shows green indicator for idle', () => {
      const { container } = render(Navbar, { props: { status: 'idle' } });

      const indicator = container.querySelector('.bg-green-500');
      expect(indicator).toBeInTheDocument();
    });

    it('shows blue indicator for running', () => {
      const { container } = render(Navbar, { props: { status: 'running' } });

      const indicator = container.querySelector('.bg-blue-500');
      expect(indicator).toBeInTheDocument();
    });

    it('shows yellow indicator for paused', () => {
      const { container } = render(Navbar, { props: { status: 'paused' } });

      const indicator = container.querySelector('.bg-yellow-500');
      expect(indicator).toBeInTheDocument();
    });
  });
});
