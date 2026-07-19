const REGISTRATION_FIELDS = [
  "installation_id",
  "rustdesk_id",
  "hostname",
  "os",
  "app_version",
  "registered_at",
];

function validateRegistration(input, expectedToken) {
  if (!input || input.token !== expectedToken) {
    return { ok: false, error: "unauthorized" };
  }
  const allowed = new Set(["token"].concat(REGISTRATION_FIELDS));
  if (Object.keys(input).some((key) => !allowed.has(key))) {
    return { ok: false, error: "unexpected_field" };
  }
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  if (!uuid.test(String(input.installation_id || ""))) {
    return { ok: false, error: "invalid_installation_id" };
  }
  for (const field of REGISTRATION_FIELDS.slice(1)) {
    const value = String(input[field] || "");
    if (!value || value.length > 255) {
      return { ok: false, error: "invalid_" + field };
    }
  }
  if (!["windows", "linux", "macos"].includes(input.os)) {
    return { ok: false, error: "invalid_os" };
  }
  if (Number.isNaN(Date.parse(input.registered_at))) {
    return { ok: false, error: "invalid_registered_at" };
  }
  const cleaned = {};
  REGISTRATION_FIELDS.forEach((field) => cleaned[field] = String(input[field]));
  return { ok: true, value: cleaned };
}
