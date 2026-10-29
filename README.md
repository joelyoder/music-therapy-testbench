# Music Therapy Test Bench

Internal tool for testing session-idea generation across models and prompts.
Team logs in with Google, edits the system prompt in the UI, runs one or several models side by side, and rates results. Every run is logged (model, exact prompt, cost, latency, rating, notes) so you can compare cost vs quality.

**Not for client data.** Do not enter names or identifying details. This is not HIPAA-ready.

## Run locally

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # fill in openrouter_api_key
DEV_MODE=1 streamlit run app.py     # DEV_MODE skips login; local only, never set on a host
```
Without `database_url` it uses a local SQLite file. Tests: `python -m pytest tests`.

## Setup checklist

1. **OpenRouter**: create an account, create an API key, and **set a monthly credit/spend limit on that key**. This is your real protection against runaway cost.
2. **Models**: edit `models.json` to the models you want in the picker (ids from openrouter.ai/models). Verify ids and prices; the shipped list is a starting guess.
3. **Database**: create a free Postgres on Neon or Supabase and copy the connection string to `database_url`. (Streamlit Community Cloud wipes local files, so SQLite there would lose your history.)
4. **Google sign-in**: in Google Cloud Console, create an OAuth client (type: Web application). Add the redirect URI `https://YOUR-APP.streamlit.app/oauth2callback` (and `http://localhost:8501/oauth2callback` for local testing). Put client id/secret in the `[auth]` section of secrets. List allowed team emails in `allowed_emails`. Anyone else can sign in with Google but is turned away.
5. **Deploy**: on share.streamlit.io, point at this repo, main file `app.py`, and paste your secrets into the app's Secrets box. (Render works too: `pip install -r requirements.txt`, start command `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`, secrets as environment variables.)

Fallback if Google setup is a hassle: remove the `[auth]` section and set `app_password` instead.

## Safety rails built in

- Fails closed: with no login configured, nobody gets in.
- API key is only used server-side; the browser never sees it.
- Starred models come from `models.json`; the "More models" picker lists all of OpenRouter live, hiding anything above `max_output_price_per_m` unless the user ticks the opt-in box. Output tokens capped by `max_tokens_cap`; per-user daily run limit.

## Example sets

Prompts can include a swappable set of example sessions (to teach structure, tone and quality) via the `{{examples}}` placeholder. On the **Example Sets** page, upload `library.json`, pick entries, and save a set; or paste/edit text directly. Pick the set in the Playground; every run records which set was used, so History can compare sets. The upload is read in-session only and never stored; only the entries you pick are saved.

Regenerate the library file with: `python -I scripts/build_library.py EXPORT.xml data/`

## Layout

- `app.py` entry + navigation; `views/playground.py` generate/compare; `views/history.py` runs table, model comparison, CSV export; `views/examples.py` build/save example sets
- `scripts/build_library.py` cleans a WordPress export into `library.json` (kept out of git)
- `lib/` auth, db (SQLAlchemy; SQLite or Postgres), llm (OpenRouter via OpenAI SDK)
