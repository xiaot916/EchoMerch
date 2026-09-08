import { fileURLToPath, URL } from "node:url"
import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

// The API binds to all interfaces, so loopback is the most reliable target
// for the Vite process. Using the machine hostname can resolve to an
// unreachable IPv6 interface on Windows and intermittently turn auth calls
// into proxy timeouts.
const apiProxyTarget = process.env.ECHO_API_PROXY_TARGET || "http://127.0.0.1:8001"

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // Listen on every network interface so devices on the same LAN can open
    // the development dashboard through this computer's LAN IP.
    host: "0.0.0.0",
    port: 9568,
    proxy: {
      "/api": apiProxyTarget,
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          echartsCore: [
            "echarts/core",
            "echarts/components",
            "echarts/renderers",
          ],
          echartsCharts: ["echarts/charts"],
        },
      },
    },
  },
})
