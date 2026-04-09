const { createProxyMiddleware } = require('http-proxy-middleware');

/** Forwards API routes to FastAPI. Required for multipart /upload (CRA's package.json proxy is unreliable). */
module.exports = function (app) {
  const target =
    process.env.REACT_APP_PROXY_TARGET || 'http://127.0.0.1:8000';

  app.use(
    createProxyMiddleware(
      (pathname) =>
        pathname === '/health' ||
        pathname === '/upload' ||
        pathname === '/openapi.json' ||
        pathname.startsWith('/docs'),
      { target, changeOrigin: true }
    )
  );
};
