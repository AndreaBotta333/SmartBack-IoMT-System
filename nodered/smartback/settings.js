module.exports = {
  flowFile: process.env.FLOWS || "flows.json",
  // flows_cred.json contiene solo riferimenti ${ENV_VAR}, mai token reali.
  credentialSecret: false,
  uiPort: process.env.PORT || 1880,
  diagnostics: { enabled: true, ui: true },
  runtimeState: { enabled: false, ui: false },
  functionExternalModules: false,
  editorTheme: { projects: { enabled: false } }
};
