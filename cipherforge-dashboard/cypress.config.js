const { defineConfig } = require('cypress');

module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://localhost:4300',
    supportFile: false,
    video: false,
    viewportWidth: 1366,
    viewportHeight: 768
  },
  env: {
    apiBaseUrl: 'http://localhost:8081'
  }
});
