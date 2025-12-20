-- Add job_id column (rename batch_id conceptually - will use batch_id as job_id for existing data)
ALTER TABLE tasks ADD COLUMN job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE;
ALTER TABLE tasks ADD COLUMN work_batch_id INTEGER REFERENCES work_batches(id) ON DELETE CASCADE;

-- Copy batch_id to job_id for existing rows
UPDATE tasks SET job_id = batch_id WHERE job_id IS NULL;

-- Create index on work_batch_id
CREATE INDEX IF NOT EXISTS idx_tasks_work_batch ON tasks(work_batch_id);
CREATE INDEX IF NOT EXISTS idx_tasks_job ON tasks(job_id);
