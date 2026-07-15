module.exports = {
  flowFile: process.env.FLOWS || "flows.json",
  uiPort: process.env.PORT || 1880,
  diagnostics: { enabled: true, ui: true },
  runtimeState: { enabled: false, ui: false },
  functionExternalModules: false,
  editorTheme: { projects: { enabled: false } }
};
