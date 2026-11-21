import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, lazyPlugins } from "vite-plus";

// https://viteplus.dev/config/
export default defineConfig({
  fmt: { ignorePatterns: ["src/routeTree.gen.ts"] },
  lint: {
    plugins: ["react", "typescript", "oxc"],
    // Generated (routeTree) and shadcn-vendored files are not ours to lint.
    ignorePatterns: ["src/routeTree.gen.ts", "src/components/ui/**"],
    rules: {
      "react/rules-of-hooks": "error",
      // TanStack file routes export `Route` next to their components by design.
      "react/only-export-components": "off",
      "vite-plus/prefer-vite-plus-imports": "error",
      // Never the browser's own alert/confirm/prompt: use the shadcn dialogs (ConfirmDialog,
      // NameDialog in src/components). See frontend/CLAUDE.md.
      "no-alert": "error",
    },
    options: { typeAware: true, typeCheck: true },
    jsPlugins: [{ name: "vite-plus", specifier: "vite-plus/oxlint-plugin" }],
  },
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    port: 5184,
    // Never drift to 5185: the API's links and CORS expect this port. `make web` frees it first.
    strictPort: true,
    // Dev proxy: the browser talks to one origin; Vite forwards API traffic to Django.
    // Keeps the browser's Host, so links Django builds point at this server.
    proxy: {
      "/api": { target: "http://localhost:8010", changeOrigin: false },
      // The events websocket (src/network/socket.ts), served by the same Django process.
      "/ws": { target: "ws://localhost:8010", ws: true, changeOrigin: false },
    },
  },
  plugins: lazyPlugins(() => [
    // Must come before react(): generates src/routeTree.gen.ts from the src/routes/ folders.
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ]),
});
