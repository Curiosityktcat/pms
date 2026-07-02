/// <reference types="vite/client" />

interface ImportMetaEnv {
  // 测试实例构建时设为 'test'（见 run_test.sh），正式构建为空
  readonly VITE_PMS_ENV?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
