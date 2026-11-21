// Railway Infrastructure as Code for the Mutual Fund FAQ Assistant — see Docs/deployment-plan.md.
//
// Apply with the Railway CLI (Railway does not read this folder during deploys):
//   railway login && railway link
//   railway config plan     # review first: services, volume, variables (secrets redacted)
//   railway config apply
//
// Before the first apply:
//   1. REPO below is the GitHub repository (public: SNAPSHOT_TOKEN not needed).
//   2. Set the secrets as sealed variables (dashboard or `railway variables --service api --set ...`):
//        api:       GROQ_API_KEY, REFRESH_TOKEN (SNAPSHOT_TOKEN only if the repo is made private)
//        streamlit: API_URL = http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000/api
//   3. Dashboard-only: generate domains, restart policy (on failure), watch paths, deploy branch
//      master, "Wait for CI" (deployment-plan.md §D2.3).
// Do NOT add railway.json / railway.toml: Config as Code is deprecated (cutoff 2026-12-01).

import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

const REPO = "sarveshnigalye/Mutual-Fund-Assistant";

export default defineRailway(() => {
  // Persistent data for the api service: index, snapshot metadata, SQLite chat history.
  const data = volume("mf-data", { sizeMB: 1024 });

  const api = service("api", {
    source: github(REPO, { branch: "master" }),
    start: "python scripts/railway_start.py", // startup snapshot sync, then uvicorn on [::]:$PORT
    healthcheck: "/api/health",
    healthcheckTimeout: 120, // first boot downloads the snapshot before serving
    volumeMounts: { "/data": data },
    env: {
      RAILPACK_PYTHON_VERSION: "3.11", // same as the GitHub Actions build: pickles must match
      PORT: "8000", // fixed so the streamlit service can address it privately
      LLM_PROVIDER: "groq",
      GROQ_MODEL: "openai/gpt-oss-120b",
      LLM_MODEL: "openai/gpt-oss-120b",
      VECTOR_DB_PROVIDER: "local",
      VECTORSTORE_PATH: "/data/vectorstore",
      CHROMA_DB_PATH: "/data/chroma",
      DATA_METADATA_PATH: "/data/metadata.json",
      CHAT_DB_PATH: "/data/chat.db",
      INDEX_RELOAD_CHECK_SECONDS: "60",
      SNAPSHOT_REPO: REPO,
      SNAPSHOT_BRANCH: "data-snapshot",
      SNAPSHOT_POLL_HOURS: "6",
      RATE_LIMIT_PER_MINUTE: "20",
      MAX_REQUEST_BYTES: "16384",
      TZ: "Asia/Kolkata",
      GROQ_API_KEY: preserve(),
      REFRESH_TOKEN: preserve(),
      // Public repo: no SNAPSHOT_TOKEN. If the repo is made private, add `SNAPSHOT_TOKEN: preserve(),`
      // and set a read-only fine-grained token as a sealed variable.
    },
  });

  // Optional second frontend; delete this service (and from `resources`) to keep only /app.
  const streamlit = service("streamlit", {
    source: github(REPO, { branch: "master" }),
    start: "python scripts/railway_start.py streamlit",
    env: {
      RAILPACK_PYTHON_VERSION: "3.11",
      API_URL: preserve(), // http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000/api (set in the dashboard)
    },
  });

  return project("hdfc-mf-faq", { resources: [api, streamlit, data] });
});
