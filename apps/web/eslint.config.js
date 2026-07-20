import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "playwright-report/**", "test-results/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-undef": "off",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["src/viewer/CadViewport.tsx", "src/viewer/CameraRig.tsx"],
    rules: {
      // Three.js cameras and materials are intentionally imperative objects.
      "react-hooks/immutability": "off",
      // This app does not enable React Compiler; stable callbacks still protect Three.js effects.
      "react-hooks/preserve-manual-memoization": "off",
    },
  },
  {
    files: ["src/workspace/WorkspaceController.tsx"],
    rules: {
      // Initial hydration owns async local/server fallbacks and reports them into component state.
      "react-hooks/set-state-in-effect": "off",
    },
  },
);
