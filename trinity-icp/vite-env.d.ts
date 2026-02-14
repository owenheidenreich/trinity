/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LIGHTHOUSE_API_KEY: string;
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
