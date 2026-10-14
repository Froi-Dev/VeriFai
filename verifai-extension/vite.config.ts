import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'
import { copyFileSync, mkdirSync, existsSync } from 'fs'

/**
 * Custom Vite plugin to copy the content script files (JS + CSS)
 * into dist/content/ after the build finishes.
 *
 * The content script is plain vanilla JS (not a Vite entry point)
 * because it must run as a simple injected script in web pages
 * without module syntax or React dependencies.
 */
function copyContentScript() {
  return {
    name: 'copy-content-script',
    writeBundle() {
      const outDir = resolve(__dirname, 'dist', 'content')
      if (!existsSync(outDir)) {
        mkdirSync(outDir, { recursive: true })
      }

      // Copy content.js
      copyFileSync(
        resolve(__dirname, 'src', 'content', 'content.js'),
        resolve(outDir, 'content.js')
      )

      // Copy content.css
      copyFileSync(
        resolve(__dirname, 'src', 'content', 'content.css'),
        resolve(outDir, 'content.css')
      )

      console.log('[Verif.AI] Content script copied to dist/content/')
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), copyContentScript()],
  // Use relative paths — Chrome extensions can't resolve absolute /assets/ paths
  base: '',
  build: {
    // Output directory for the extension bundle
    outDir: 'dist',
    emptyOutDir: true,

    // Multi-page entry points: popup + cropper
    rollupOptions: {
      input: {
        popup: resolve(__dirname, 'popup.html'),
        cropper: resolve(__dirname, 'cropper.html'),
      },
      output: {
        // Keep filenames predictable (no hashes) for extension context
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
})
