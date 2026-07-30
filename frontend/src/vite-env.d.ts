/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the FastAPI backend, e.g. http://localhost:8000 */
  readonly VITE_API_URL: string
  /** Demo bearer token. Not real auth — see the README. */
  readonly VITE_DEMO_TOKEN: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
