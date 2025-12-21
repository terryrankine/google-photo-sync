import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import StatsCard from './StatsCard.svelte';

describe('StatsCard', () => {
  it('renders title and value', () => {
    render(StatsCard, { props: { title: 'Total Files', value: 1234 } });

    expect(screen.getByText('Total Files')).toBeInTheDocument();
    expect(screen.getByText('1234')).toBeInTheDocument();
  });

  it('renders subtitle when provided', () => {
    render(StatsCard, {
      props: { title: 'Files', value: 100, subtitle: '50 uploaded' }
    });

    expect(screen.getByText('50 uploaded')).toBeInTheDocument();
  });

  it('does not render subtitle when not provided', () => {
    const { container } = render(StatsCard, {
      props: { title: 'Files', value: 100 }
    });

    // No subtitle text should be present
    expect(container.textContent).not.toContain('uploaded');
  });

  it('handles zero value', () => {
    render(StatsCard, { props: { title: 'Empty', value: 0 } });

    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('handles large numbers', () => {
    render(StatsCard, { props: { title: 'Large', value: 1000000 } });

    expect(screen.getByText('1000000')).toBeInTheDocument();
  });

  it('handles string values', () => {
    render(StatsCard, { props: { title: 'Size', value: '1.5 GB' } });

    expect(screen.getByText('1.5 GB')).toBeInTheDocument();
  });
});
