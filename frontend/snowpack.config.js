module.exports = {
  // "extends": "@snowpack/app-scripts-react",
  mount: {
    public: '/',
    src: '/_dist_',
  },
  proxy: {
    "/ws": {
      target: "ws://localhost:8234",
      ws: true
    }
  },
  plugins: [
    '@snowpack/plugin-react-refresh',
    '@snowpack/plugin-dotenv',
  ],
};
