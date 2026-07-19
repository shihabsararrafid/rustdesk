"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const ROOT = path.join(__dirname, "..");
const CORE_PATH = path.join(ROOT, "deploy/google-apps-script/RegistrationCore.gs");
const CODE_PATH = path.join(ROOT, "deploy/google-apps-script/Code.gs");

function loadGs(filePath, context) {
  const code = fs.readFileSync(filePath, "utf8");
  vm.runInNewContext(code, context, { filename: filePath });
}

function loadValidation() {
  const context = { console, Date, Number, Object, String, Array, Set, RegExp };
  loadGs(CORE_PATH, context);
  return context.validateRegistration;
}

const validPayload = () => ({
  token: "token",
  installation_id: "3d9d36e2-70c1-4c1d-a63d-cf45f314e922",
  rustdesk_id: "123456789",
  hostname: "front-desk",
  os: "windows",
  app_version: "1.4.9",
  registered_at: "2026-07-19T12:00:00Z",
});

function createMockRuntime(options = {}) {
  const properties = {
    SHEET_ID: "sheet-id",
    RECIPIENT_EMAIL: "ops@example.com",
    CLIENT_TOKEN: "token",
    ...options.properties,
  };

  const rows = [null];
  if (options.headers !== false) {
    rows.push([
      "installation_id",
      "rustdesk_id",
      "hostname",
      "os",
      "app_version",
      "registered_at_utc",
      "received_at_utc",
      "email_status",
      "email_error",
    ]);
  }

  let locked = false;
  const emails = [];
  let mailShouldFail = options.mailShouldFail || false;

  function createTextFinder(searchText) {
    return {
      matchEntireCell() {
        return this;
      },
      findNext() {
        for (let rowIndex = 2; rowIndex < rows.length; rowIndex += 1) {
          if (String(rows[rowIndex][0]) === String(searchText)) {
            return { getRow: () => rowIndex };
          }
        }
        return null;
      },
    };
  }

  const sheet = {
    getLastRow() {
      return rows.length - 1;
    },
    appendRow(values) {
      rows.push(values.slice());
    },
    setFrozenRows() {},
    getRange(startRow, startColumn, third, fourth) {
      const numRows = third;
      const numColumns = fourth;
      return {
        createTextFinder(searchText) {
          return createTextFinder(searchText);
        },
        getValues() {
          const result = [];
          for (let r = 0; r < numRows; r += 1) {
            const row = rows[startRow + r];
            if (!row) continue;
            result.push(row.slice(startColumn - 1, startColumn - 1 + numColumns));
          }
          return result;
        },
        setValues(values) {
          for (let r = 0; r < values.length; r += 1) {
            const targetRow = startRow + r;
            if (!rows[targetRow]) rows[targetRow] = [];
            for (let c = 0; c < values[r].length; c += 1) {
              rows[targetRow][startColumn - 1 + c] = values[r][c];
            }
          }
        },
      };
    },
  };

  const spreadsheet = {
    getSheetByName(name) {
      return name === "Registrations" ? sheet : null;
    },
    insertSheet(name) {
      assert.equal(name, "Registrations");
      return sheet;
    },
  };

  const context = {
    console,
    Date,
    JSON,
    Number,
    Object,
    String,
    Array,
    Set,
    RegExp,
    LockService: {
      getScriptLock() {
        return {
          waitLock() {
            assert.equal(locked, false, "lock already held");
            locked = true;
          },
          releaseLock() {
            locked = false;
          },
        };
      },
    },
    SpreadsheetApp: {
      openById(id) {
        assert.equal(id, properties.SHEET_ID);
        return spreadsheet;
      },
      flush() {},
    },
    PropertiesService: {
      getScriptProperties() {
        return {
          getProperty(key) {
            return properties[key] || null;
          },
        };
      },
    },
    ContentService: {
      MimeType: { JSON: "JSON" },
      createTextOutput(value) {
        return {
          _value: value,
          setMimeType(mimeType) {
            this._mimeType = mimeType;
            return this;
          },
        };
      },
    },
    MailApp: {
      sendEmail(to, subject, body) {
        if (mailShouldFail) {
          throw new Error(options.mailError || "mail delivery failed");
        }
        emails.push({ to, subject, body });
      },
    },
    __rows: rows,
    __emails: emails,
    __setProperty(key, value) {
      properties[key] = value;
    },
    setMailShouldFail(value, error) {
      mailShouldFail = value;
      if (error) options.mailError = error;
    },
  };

  loadGs(CORE_PATH, context);
  loadGs(CODE_PATH, context);
  return context;
}

function parseResponse(output) {
  assert.equal(output._mimeType, "JSON");
  return JSON.parse(output._value);
}

test("accepts the approved schema", () => {
  const validateRegistration = loadValidation();
  const result = validateRegistration(validPayload(), "token");
  assert.equal(result.ok, true);
});

test("rejects invalid token and unapproved fields", () => {
  const validateRegistration = loadValidation();
  assert.equal(validateRegistration({ token: "wrong" }, "token").ok, false);
  const payload = validPayload();
  payload.public_ip = "203.0.113.1";
  assert.equal(validateRegistration(payload, "token").ok, false);
});

test("rejects missing or invalid expected token before payload comparison", () => {
  const validateRegistration = loadValidation();
  const payload = validPayload();
  assert.equal(validateRegistration(payload, null).ok, false);
  assert.equal(validateRegistration(payload, "").ok, false);
  assert.equal(validateRegistration(payload, undefined).ok, false);
  assert.equal(validateRegistration(payload, 123).ok, false);
});

test("rejects payload token null", () => {
  const validateRegistration = loadValidation();
  const payload = validPayload();
  payload.token = null;
  assert.equal(validateRegistration(payload, "token").ok, false);
});

test("doPost accepts a valid new registration and sends one email", () => {
  const runtime = createMockRuntime();
  const payload = validPayload();
  const response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(payload) } })
  );

  assert.deepEqual(response, { accepted: true, duplicate: false });
  assert.equal(runtime.__rows.length, 3);
  assert.equal(runtime.__rows[2][7], "email_sent");
  assert.equal(runtime.__rows[2][8], "");
  assert.equal(runtime.__emails.length, 1);
  assert.match(runtime.__emails[0].subject, /123456789/);
  assert.doesNotMatch(JSON.stringify(runtime.__rows), /"token"/);
});

test("doPost returns duplicate for an existing installation UUID without resending email", () => {
  const runtime = createMockRuntime();
  const payload = validPayload();
  runtime.doPost({ postData: { contents: JSON.stringify(payload) } });
  const response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(payload) } })
  );

  assert.deepEqual(response, { accepted: true, duplicate: true });
  assert.equal(runtime.__rows.length, 3);
  assert.equal(runtime.__emails.length, 1);
});

test("doPost rejects invalid token", () => {
  const runtime = createMockRuntime();
  const payload = validPayload();
  payload.token = "wrong";
  const response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(payload) } })
  );

  assert.deepEqual(response, { accepted: false, error: "unauthorized" });
  assert.equal(runtime.__rows.length, 2);
  assert.equal(runtime.__emails.length, 0);
});

test("doPost rejects malformed JSON", () => {
  const runtime = createMockRuntime();
  const response = parseResponse(
    runtime.doPost({ postData: { contents: "{" } })
  );

  assert.deepEqual(response, { accepted: false, error: "internal_error" });
});

test("doPost rejects unexpected fields", () => {
  const runtime = createMockRuntime();
  const payload = validPayload();
  payload.public_ip = "203.0.113.1";
  const response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(payload) } })
  );

  assert.deepEqual(response, { accepted: false, error: "unexpected_field" });
});

test("sequential duplicate requests remain idempotent under lock", () => {
  const runtime = createMockRuntime();
  const cleaned = runtime.validateRegistration(validPayload(), "token").value;
  const properties = runtime.PropertiesService.getScriptProperties();
  const first = runtime.recordRegistration_(cleaned, properties);
  const second = runtime.recordRegistration_(cleaned, properties);

  assert.equal(first.accepted, true);
  assert.equal(first.duplicate, false);
  assert.equal(second.accepted, true);
  assert.equal(second.duplicate, true);
  assert.equal(runtime.__rows.length, 3);
  assert.equal(runtime.__emails.length, 1);
});

test("doPost rejects missing CLIENT_TOKEN without creating rows", () => {
  const runtime = createMockRuntime({
    properties: { SHEET_ID: "sheet-id", RECIPIENT_EMAIL: "ops@example.com", CLIENT_TOKEN: "" },
  });
  const response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(validPayload()) } })
  );

  assert.deepEqual(response, { accepted: false, error: "unauthorized" });
  assert.equal(runtime.__rows.length, 2);
  assert.equal(runtime.__emails.length, 0);
});

test("doPost rejects missing SHEET_ID without creating rows", () => {
  const runtime = createMockRuntime({
    properties: { SHEET_ID: "", RECIPIENT_EMAIL: "ops@example.com", CLIENT_TOKEN: "token" },
  });
  const response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(validPayload()) } })
  );

  assert.deepEqual(response, { accepted: false, error: "missing_sheet_id" });
  assert.equal(runtime.__rows.length, 2);
  assert.equal(runtime.__emails.length, 0);
});

test("doPost rejects missing RECIPIENT_EMAIL without creating rows", () => {
  const runtime = createMockRuntime({
    properties: { SHEET_ID: "sheet-id", RECIPIENT_EMAIL: "", CLIENT_TOKEN: "token" },
  });
  const response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(validPayload()) } })
  );

  assert.deepEqual(response, { accepted: false, error: "missing_recipient_email" });
  assert.equal(runtime.__rows.length, 2);
  assert.equal(runtime.__emails.length, 0);
});

test("doPost accepts a registration after deployment properties are corrected", () => {
  const runtime = createMockRuntime({
    properties: { SHEET_ID: "", RECIPIENT_EMAIL: "ops@example.com", CLIENT_TOKEN: "token" },
  });
  const payload = validPayload();
  let response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(payload) } })
  );

  assert.deepEqual(response, { accepted: false, error: "missing_sheet_id" });
  assert.equal(runtime.__rows.length, 2);
  assert.equal(runtime.__emails.length, 0);

  runtime.__setProperty("SHEET_ID", "sheet-id");
  response = parseResponse(
    runtime.doPost({ postData: { contents: JSON.stringify(payload) } })
  );

  assert.deepEqual(response, { accepted: true, duplicate: false });
  assert.equal(runtime.__rows.length, 3);
  assert.equal(runtime.__rows[2][7], "email_sent");
  assert.equal(runtime.__emails.length, 1);
});

test("deliverEmail_ records bounded email_failed error", () => {
  const runtime = createMockRuntime({ mailShouldFail: true, mailError: "x".repeat(700) });
  const payload = validPayload();
  runtime.recordRegistration_(payload, runtime.PropertiesService.getScriptProperties());

  assert.equal(runtime.__rows[2][7], "email_failed");
  assert.equal(runtime.__rows[2][8].length, 500);
  assert.equal(runtime.__emails.length, 0);
});

test("retryFailedEmails retries only explicit email_failed rows", () => {
  const runtime = createMockRuntime({ mailShouldFail: true });
  const payload = validPayload();
  runtime.recordRegistration_(payload, runtime.PropertiesService.getScriptProperties());
  assert.equal(runtime.__rows[2][7], "email_failed");

  runtime.__rows.push([
    payload.installation_id + "-pending",
    "999",
    "other",
    "linux",
    "2.0.0",
    "2026-07-19T13:00:00Z",
    "2026-07-19T13:00:01Z",
    "email_pending",
    "",
  ]);

  runtime.setMailShouldFail(false);
  runtime.retryFailedEmails();

  assert.equal(runtime.__rows[2][7], "email_sent");
  assert.equal(runtime.__rows[3][7], "email_pending");
  assert.equal(runtime.__emails.length, 1);
});

test("doPost rejects oversized payloads before JSON parse", () => {
  const runtime = createMockRuntime();
  const oversized = "x".repeat(4097);
  const response = parseResponse(
    runtime.doPost({ postData: { contents: oversized } })
  );
  assert.equal(response.accepted, false);
  assert.equal(response.error, "payload_too_large");
  assert.equal(runtime.__rows.length, 2);
  assert.equal(runtime.__emails.length, 0);
});
