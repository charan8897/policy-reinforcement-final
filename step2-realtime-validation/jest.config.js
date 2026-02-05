module.exports = {
  testEnvironment: 'jsdom',
  collectCoverageFrom: [
    'modules/**/*.js',
    '!modules/**/*.test.js',
  ],
  testMatch: [
    '**/__tests__/**/*.js',
    '**/*.test.js',
  ],
  verbose: true,
};
