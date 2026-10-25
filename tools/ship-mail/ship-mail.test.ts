import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

// Jest (and every project gate) runs from the repository root.
const REPO_ROOT = process.cwd();
const SCRIPT = join(REPO_ROOT, "scripts", "ship-mail.sh");

const SID_A = "ses_testmailboxA0000000000000";
const SID_B = "ses_testmailboxB0000000000000";
const SID_UNREGISTERED = "ses_testmailboxZ000000000000";

interface RunResult {
  stdout: string;
  status: number;
}

interface ExecError {
  status?: number;
  stdout?: string | Buffer;
}

let home: string;
let registry: string;

function run(args: string[]): RunResult {
  try {
    const stdout = execFileSync("bash", [SCRIPT, ...args], {
      encoding: "utf8",
      env: {
        ...process.env,
        SHIP_MAIL_HOME: home,
        SHIP_MAIL_REGISTRY: registry,
      },
    });
    return { stdout, status: 0 };
  } catch (error) {
    const err = error as ExecError;
    const raw = err.stdout ?? "";
    return {
      stdout: typeof raw === "string" ? raw : raw.toString("utf8"),
      status: err.status ?? -1,
    };
  }
}

function inboxFiles(sid: string): string[] {
  const dir = join(home, "inbox", sid);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((name) => name.endsWith(".md"))
    .sort();
}

function readFiles(sid: string): string[] {
  const dir = join(home, "inbox", sid, "read");
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((name) => name.endsWith(".md"))
    .sort();
}

beforeEach(() => {
  home = mkdtempSync(join(tmpdir(), "ship-mail-"));
  const regDir = mkdtempSync(join(tmpdir(), "ship-mail-registry-"));
  registry = join(regDir, "peer-registry.md");
  const rows = [
    `| Тест-А | ${SID_A} | test | /tmp | test |`,
    `| Тест-Б | ${SID_B} | test | /tmp | test |`,
  ].join("\n");
  writeRegistry(rows);
});

function writeRegistry(content: string): void {
  writeFileSync(registry, `${content}\n`, "utf8");
}

afterEach(() => {
  rmSync(home, { recursive: true, force: true });
  rmSync(dirname(registry), { recursive: true, force: true });
});

describe("ship-mail mailbox bus", () => {
  it("delivers a letter as one file with OKF frontmatter", () => {
    const res = run([
      "send",
      "--to",
      SID_B,
      "--from",
      SID_A,
      "--title",
      'Привет "хаб"',
      "--ref",
      "pilot-1",
      "--text",
      "тело письма",
    ]);
    expect(res.status).toBe(0);
    expect(res.stdout).toContain("DELIVERED");

    const files = inboxFiles(SID_B);
    expect(files).toHaveLength(1);
    const letter = readFileSync(join(home, "inbox", SID_B, files[0]), "utf8");
    expect(letter).toContain("type: Letter");
    expect(letter).toContain(`from: ${SID_A}`);
    expect(letter).toContain(`to: ${SID_B}`);
    expect(letter).toContain('ref: "pilot-1"');
    expect(letter).toContain("id: ");
    expect(letter).toContain("тело письма");
  });

  it("is idempotent for the same body+sender+day", () => {
    const first = run([
      "send",
      "--to",
      SID_B,
      "--from",
      SID_A,
      "--text",
      "одна и та же речь",
    ]);
    expect(first.status).toBe(0);
    expect(inboxFiles(SID_B)).toHaveLength(1);

    const second = run([
      "send",
      "--to",
      SID_B,
      "--from",
      SID_A,
      "--text",
      "одна и та же речь",
    ]);
    expect(second.status).toBe(3);
    expect(inboxFiles(SID_B)).toHaveLength(1);
  });

  it("gives different letters different ids", () => {
    run(["send", "--to", SID_B, "--from", SID_A, "--text", "первое"]);
    run(["send", "--to", SID_B, "--from", SID_A, "--text", "второе"]);
    expect(inboxFiles(SID_B)).toHaveLength(2);
  });

  it("inbox lists, show prints, ack moves the letter to read/", () => {
    run([
      "send",
      "--to",
      SID_B,
      "--from",
      SID_A,
      "--title",
      "тема",
      "--text",
      "прочти меня",
    ]);

    const inbox = run(["inbox", SID_B]);
    expect(inbox.status).toBe(0);
    expect(inbox.stdout).toContain("unread: 1");
    expect(inbox.stdout).toContain(SID_A);
    expect(inbox.stdout).toContain("тема");

    const shown = run(["show", SID_B]);
    expect(shown.status).toBe(0);
    expect(shown.stdout).toContain("прочти меня");

    const acked = run(["ack", SID_B, "all"]);
    expect(acked.status).toBe(0);
    expect(acked.stdout).toContain("ACK 1");

    const after = run(["inbox", SID_B]);
    expect(after.stdout).toContain("unread: 0");

    const status = run(["status", SID_B]);
    expect(status.stdout).toContain("unread: 0");
    expect(status.stdout).toContain("read: 1");
    expect(readFiles(SID_B)).toHaveLength(1);
  });

  it("refuses an unregistered recipient and writes nothing", () => {
    const res = run([
      "send",
      "--to",
      SID_UNREGISTERED,
      "--from",
      SID_A,
      "--text",
      "в никуда",
    ]);
    expect(res.status).toBe(4);
    expect(existsSync(join(home, "inbox", SID_UNREGISTERED))).toBe(false);
  });

  it("refuses an unregistered sender", () => {
    const res = run([
      "send",
      "--to",
      SID_B,
      "--from",
      SID_UNREGISTERED,
      "--text",
      "подделка",
    ]);
    expect(res.status).toBe(4);
    expect(inboxFiles(SID_B)).toHaveLength(0);
  });

  it("fails cleanly when the registry file is missing", () => {
    rmSync(dirname(registry), { recursive: true, force: true });
    const res = run([
      "send",
      "--to",
      SID_B,
      "--from",
      SID_A,
      "--text",
      "нет реестра",
    ]);
    expect(res.status).toBe(5);
    expect(inboxFiles(SID_B)).toHaveLength(0);
  });
});
