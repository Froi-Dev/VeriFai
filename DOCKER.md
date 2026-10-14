# Run VerifAI in Docker Desktop

Use Docker Desktop with Linux containers. From the project root:

```powershell
docker compose up --build -d
docker compose ps
```

Open **http://localhost:5173**. The five services appear together as `verifai`
in Docker Desktop, where you can stop/start them and view their logs.
The API is also available at http://localhost:8000/docs. Register a new account;
this stack starts with its own empty PostgreSQL database, not the original user's
accounts or scan history. Data persists in Docker named volumes across restarts.

## Shared keys and first setup

The prepared workspace includes a private **root `.env`** containing the authorized
shared provider keys and newly generated database/JWT secrets. Include that file
when sharing this folder privately with the team. It is ignored by Git and excluded
from Docker build contexts; keys are loaded only when containers start.
Do not use the backend's original `.env` as the Docker configuration: it contains
machine-specific database and model paths.

For a fresh Git checkout without root `.env`, generate it using Docker (no local
Python installation needed):

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace python:3.11-slim python docker/prepare_env.py
```

Then fill in `GEMINI_API_KEYS` and at least one search provider (`SERPER_API_KEYS`,
`SEARCHAPI_API_KEY`, or Google API key plus CSE ID). If an authorized backend `.env`
is present, add `--copy-shared-keys` to the generation command to copy only provider
settings. Existing root `.env` files are never overwritten. Use hexadecimal database
passwords because the password is interpolated into a database URL.

Gemini and web search require internet access and valid provider quotas. The default
matches the current Gemini analyzer configuration. PaddleOCR is not installed (it
is also absent from the current local environment); if Gemini OCR is unavailable,
the optional Paddle fallback cannot run. No API response or analyzer result is mocked.

## Password reset and extension

Password-reset mail is captured locally by Mailpit at **http://localhost:8025**.
To deliver real email, set the SMTP variables shown in `.env.example` and recreate
the backend with `docker compose up -d`. Mailpit is for local testing only.

The included browser extension is installed separately in Chrome/Edge using Load
unpacked on `verifai-extension/dist/`, or the app's download. The frontend Docker
build compiles and packages this extension automatically. For a local unpacked
build, run `npm ci` and `npm run build` inside `verifai-extension`. The default ports 5173
and 8000 match the extension's connection URLs.

## Optional trained text model

The large checkpoint is not included in Git or the default image. Copy the complete
`xlmr-ai-human-v11-latest-gen` directory (weights, config, tokenizer, calibration)
to `models/text`, or set `TEXT_MODEL_HOST_PATH` in root `.env` to its absolute path.
Then run:

```powershell
docker compose -f compose.yaml -f compose.local-model.yaml up --build -d
```

This builds a larger image with CPU PyTorch/Transformers and mounts the checkpoint
read-only. Allow several GB of Docker memory and extra startup time. Image/news
analysis still requires the provider keys. For Gemini again, use the default
`docker compose up --build -d` command.

## Lifecycle and troubleshooting

```powershell
docker compose logs --tail=100 backend
docker compose down
docker compose up -d
```

`down` preserves the database. **`docker compose down -v` deletes accounts, scan
history, cached results, and logs.** Keep the same `.env` when restarting an existing
database volume; changing its password does not change the stored database password.

The Dockerfile has separate `frontend`, `backend`, and optional `backend-local`
targets. Compose builds the correct targets and starts PostgreSQL, Redis, and mail;
a standalone `docker build` does not start those dependent services.

Ports bind to localhost. This is a local Docker Desktop setup, not a public HTTPS
deployment. Do not expose it publicly without configuring production security,
TLS, real SMTP, and database access controls.
