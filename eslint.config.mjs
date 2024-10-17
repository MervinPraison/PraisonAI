import globals from "globals";
import * as mdx from 'eslint-plugin-mdx';

export default [
  {
    files: ["**/*.{md,mdx}"],
    processor: mdx.createRemarkProcessor({
      lintCodeBlocks: true,
    }),
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'no-var': 'error',
      'prefer-const': 'error',
    },
  },
];
