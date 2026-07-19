const SHEET_NAME = "Registrations";
const HEADERS = [
  "installation_id", "rustdesk_id", "hostname", "os", "app_version",
  "registered_at_utc", "received_at_utc", "email_status", "email_error"
];

function jsonResponse(value) {
  return ContentService
    .createTextOutput(JSON.stringify(value))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const properties = PropertiesService.getScriptProperties();
    const result = validateRegistration(
      JSON.parse((e.postData && e.postData.contents) || "{}"),
      properties.getProperty("CLIENT_TOKEN")
    );
    if (!result.ok) return jsonResponse({ accepted: false, error: result.error });
    return jsonResponse(recordRegistration_(result.value, properties));
  } catch (error) {
    console.error(String(error));
    return jsonResponse({ accepted: false, error: "internal_error" });
  }
}

function validateDeploymentProperties_(properties) {
  const sheetId = properties.getProperty("SHEET_ID");
  if (typeof sheetId !== "string" || !sheetId) {
    return { ok: false, error: "missing_sheet_id" };
  }
  const recipient = properties.getProperty("RECIPIENT_EMAIL");
  if (typeof recipient !== "string" || !recipient) {
    return { ok: false, error: "missing_recipient_email" };
  }
  return { ok: true };
}

function recordRegistration_(data, properties) {
  const config = validateDeploymentProperties_(properties);
  if (!config.ok) return { accepted: false, error: config.error };

  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const sheet = getRegistrationSheet_(properties.getProperty("SHEET_ID"));
    if (findInstallationRow_(sheet, data.installation_id)) {
      return { accepted: true, duplicate: true };
    }
    sheet.appendRow([
      data.installation_id, data.rustdesk_id, data.hostname, data.os,
      data.app_version, data.registered_at, new Date().toISOString(),
      "email_pending", ""
    ]);
    SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
  deliverEmail_(data, properties);
  return { accepted: true, duplicate: false };
}

function getRegistrationSheet_(sheetId) {
  if (!sheetId) throw new Error("missing_sheet_id");
  const spreadsheet = SpreadsheetApp.openById(sheetId);
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) sheet = spreadsheet.insertSheet(SHEET_NAME);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function findInstallationRow_(sheet, installationId) {
  if (sheet.getLastRow() < 2) return 0;
  const match = sheet.getRange(2, 1, sheet.getLastRow() - 1, 1)
    .createTextFinder(installationId)
    .matchEntireCell(true)
    .findNext();
  return match ? match.getRow() : 0;
}

function deliverEmail_(data, properties) {
  const sheet = getRegistrationSheet_(properties.getProperty("SHEET_ID"));
  const row = findInstallationRow_(sheet, data.installation_id);
  if (!row) throw new Error("registration_row_missing");
  const recipient = properties.getProperty("RECIPIENT_EMAIL");
  if (!recipient) throw new Error("recipient_missing");
  const body = [
    "A new Sasthotech Remote client registered.",
    "",
    "RustDesk ID: " + data.rustdesk_id,
    "Computer: " + data.hostname,
    "OS: " + data.os,
    "App version: " + data.app_version,
    "Registered (UTC): " + data.registered_at,
    "Installation ID: " + data.installation_id,
  ].join("\n");
  try {
    MailApp.sendEmail(
      recipient,
      "New Sasthotech Remote client: " + data.rustdesk_id,
      body
    );
    sheet.getRange(row, 8, 1, 2).setValues([["email_sent", ""]]);
  } catch (error) {
    sheet.getRange(row, 8, 1, 2).setValues([
      ["email_failed", String(error).slice(0, 500)]
    ]);
  }
}

function retryFailedEmails() {
  const properties = PropertiesService.getScriptProperties();
  const sheet = getRegistrationSheet_(properties.getProperty("SHEET_ID"));
  if (sheet.getLastRow() < 2) return;
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, HEADERS.length)
    .getValues();
  rows.forEach((row) => {
    if (row[7] !== "email_failed") return;
    deliverEmail_({
      installation_id: String(row[0]),
      rustdesk_id: String(row[1]),
      hostname: String(row[2]),
      os: String(row[3]),
      app_version: String(row[4]),
      registered_at: String(row[5]),
    }, properties);
  });
}
