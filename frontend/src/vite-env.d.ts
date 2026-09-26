/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** true（默认）读 public/mock；false 调真实 FastAPI。与 web-kb 的 USE_MOCK 口径一致。 */
  readonly VITE_USE_MOCK?: string
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
