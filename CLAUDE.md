# CLAUDE.md

GitHub: `terryrankine/google-photo-sync`. Public. Push to `main`, no PR.

Read `README.md`. It says what runs and why.

- Python 3.12, exiftool. `pytest`.
- Test first. A fault that hides behind a green page is a bug.
- Public repo: no hostnames, IPs, emails, tokens or family names in code, tests, commits.
- NAS files: never change without the owner's word. Phone files: never touch.
- One writer per database: `incoming.py` owns `incoming.db`, `google.py` owns `google.db`.
- `gphoto-web` only reads. `gphoto-incoming` and `gphoto-google` have no network.
- Google's page is undocumented. Anything read from it goes in `google.py`, with an error the owner can see.
