UPDATE jobs SET status = 'cancelled', error_message = 'Interrupted by container restart', completed_at = CURRENT_TIMESTAMP WHERE id = 26 AND status = 'running';
