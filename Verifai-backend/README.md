# VeriFai Backend

FastAPI authentication API connected to the existing PostgreSQL schema from
`Factguard.sql`.

## What is implemented

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `GET /health`
- `GET /api/v1/health` (also checks PostgreSQL)
- Argon2 password hashing for new accounts
- Verification and automatic Argon2 upgrade of the database's legacy
  Passlib `bcrypt-sha256` hashes (ordinary bcrypt is also supported)
- Revocable JWT sessions backed by the existing `session_records` table
- Authentication audit events in the existing `audit_logs` table
- CORS for the Vite development origin

The backend maps the frontend's `name` field to the existing database column
`users.username`. It does not create or alter database tables.

## Setup

Python 3.11 or newer is recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

The local `.env` is already configured for:

```text
postgresql://postgres:admin@localhost:5432/verifaiDb
```

Start PostgreSQL and confirm the dump has been restored into `verifaiDb`, then run:

```powershell
uvicorn app.main:app --reload --port 8000
```

Interactive API documentation is available at <http://localhost:8000/docs>.

Run checks with:

```powershell
ruff check .
pytest
```

## Frontend connection

Set the frontend API base URL to:

```env
VITE_API_URL=http://localhost:8000/api/v1
```

Register:

```ts
await axios.post(`${import.meta.env.VITE_API_URL}/auth/register`, {
  name,
  email,
  password,
});
```

Login:

```ts
await axios.post(`${import.meta.env.VITE_API_URL}/auth/login`, {
  email,
  password,
});
```

For protected requests, send the returned token:

```ts
await axios.get(`${import.meta.env.VITE_API_URL}/auth/me`, {
  headers: { Authorization: `Bearer ${token}` },
});
```

Do not commit `.env`; it contains database credentials and the JWT signing secret.
