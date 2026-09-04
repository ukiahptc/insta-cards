#!/usr/bin/env node
/**
 * post_instagram.mjs — Instagram Graph API(Instagram 로그인 방식)로 캐러셀 게시. 외부 의존성 없음 (Node 18+).
 *
 * 사용:
 *   node tools/post_instagram.mjs --check                                   # 토큰·계정 확인
 *   node tools/post_instagram.mjs --refresh-token                           # 장기 토큰 60일 연장
 *   node tools/post_instagram.mjs --dir cards/X --caption specs/X.caption.txt --dry-run
 *   node tools/post_instagram.mjs --dir cards/X --caption specs/X.caption.txt
 *
 * 설정 파일: ~/.config/insta-agent/config.json  (tools/config.example.json 참고)
 *   ig_user_id, access_token, api_version, api_host, base_url, github_repo, token_updated_at
 * 환경변수 INSTA_AGENT_CONFIG 로 경로 변경 가능.
 *
 * 흐름: 이미지 공개 확인(GitHub Pages) → 아이템 컨테이너 생성 → 캐러셀 컨테이너 → 상태 FINISHED 대기 → 발행 → permalink 출력
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";

const argv = process.argv.slice(2);
const flag = (n) => argv.includes(`--${n}`);
const opt = (n, def) => { const i = argv.indexOf(`--${n}`); return i >= 0 && argv[i + 1] ? argv[i + 1] : def; };

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const CONFIG_PATH = process.env.INSTA_AGENT_CONFIG || path.join(os.homedir(), ".config/insta-agent/config.json");
const log = (...a) => console.error("[insta]", ...a);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function loadConfig() {
  if (!fs.existsSync(CONFIG_PATH)) {
    throw new Error(`설정 파일이 없습니다: ${CONFIG_PATH}\n  cp tools/config.example.json ${CONFIG_PATH} 후 값을 채우세요.`);
  }
  const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  cfg.access_token = process.env.INSTA_ACCESS_TOKEN || cfg.access_token;
  cfg.ig_user_id = process.env.INSTA_USER_ID || cfg.ig_user_id;
  cfg.api_host ||= "graph.instagram.com";
  cfg.api_version ||= "v26.0";
  for (const k of ["ig_user_id", "access_token", "base_url"]) {
    if (!cfg[k] || String(cfg[k]).includes("여기에")) throw new Error(`설정값 ${k} 가 비어 있습니다 (${CONFIG_PATH})`);
  }
  return cfg;
}
function saveConfig(cfg) { fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + "\n", { mode: 0o600 }); }

async function api(cfg, method, endpoint, params = {}) {
  const url = new URL(`https://${cfg.api_host}/${cfg.api_version}/${endpoint}`);
  const body = new URLSearchParams({ ...params, access_token: cfg.access_token });
  let res;
  if (method === "GET") { url.search = body.toString(); res = await fetch(url); }
  else res = await fetch(url, { method: "POST", body });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.error) {
    const e = json.error || json;
    throw new Error(`${method} /${endpoint} 실패 (HTTP ${res.status}): ${e.message || JSON.stringify(e)}${e.error_user_msg ? " — " + e.error_user_msg : ""}`);
  }
  return json;
}

async function maybeRefreshToken(cfg, force = false) {
  const ageDays = cfg.token_updated_at ? (Date.now() - Date.parse(cfg.token_updated_at)) / 864e5 : Infinity;
  if (!force && ageDays < 30) return;
  if (!force && ageDays < 1) return; // 발급 24시간 이내는 갱신 불가
  try {
    const r = await api(cfg, "GET", "refresh_access_token", { grant_type: "ig_refresh_token" });
    cfg.access_token = r.access_token;
    cfg.token_updated_at = new Date().toISOString();
    saveConfig(cfg);
    log(`토큰 갱신 완료 (만료까지 ${Math.round(r.expires_in / 86400)}일)`);
  } catch (e) {
    if (force) throw e;
    log(`토큰 갱신 실패(계속 진행): ${e.message}`);
  }
}

function validateCaption(caption) {
  const len = [...caption].length;
  const tags = (caption.match(/#[^\s#]+/g) || []).length;
  if (len > 2200) throw new Error(`캡션이 2,200자를 넘습니다 (${len}자)`);
  if (tags > 30) throw new Error(`해시태그가 30개를 넘습니다 (${tags}개)`);
  return { len, tags };
}

function listImages(dir) {
  const abs = path.resolve(ROOT, dir);
  const files = fs.readdirSync(abs).filter((f) => /^\d+\.jpe?g$/i.test(f)).sort();
  if (!files.length) throw new Error(`이미지가 없습니다: ${abs} (01.jpg …)`);
  if (files.length > 10) throw new Error(`캐러셀은 최대 10장입니다 (${files.length}장)`);
  return files.map((f) => ({ file: path.join(abs, f), rel: path.relative(ROOT, path.join(abs, f)).split(path.sep).join("/") }));
}

function waitPagesBuild(cfg, maxSec) {
  if (!cfg.github_repo) return;
  const head = spawnSync("git", ["-C", ROOT, "rev-parse", "HEAD"], { encoding: "utf8" }).stdout.trim();
  const deadline = Date.now() + maxSec * 1000;
  for (;;) {
    const r = spawnSync("gh", ["api", `repos/${cfg.github_repo}/pages/builds/latest`], { encoding: "utf8" });
    if (r.status !== 0) { log("gh api 실패 — Pages 빌드 확인을 건너뛰고 URL 직접 확인으로 넘어갑니다"); return; }
    const b = JSON.parse(r.stdout);
    if (b.status === "built" && b.commit === head) { log("GitHub Pages 빌드 완료"); return; }
    if (b.status === "errored") throw new Error(`GitHub Pages 빌드 오류: ${b.error?.message || "?"}`);
    if (Date.now() > deadline) throw new Error("GitHub Pages 빌드가 제한 시간 안에 끝나지 않았습니다 (git push 했는지 확인)");
    log(`Pages 빌드 대기… (status=${b.status}, commit=${(b.commit || "").slice(0, 7)} / HEAD ${head.slice(0, 7)})`);
    spawnSync("sleep", ["10"]);
  }
}

async function waitUrls(images, maxSec) {
  const deadline = Date.now() + maxSec * 1000;
  for (;;) {
    const ok = await Promise.all(images.map(async (im) => {
      try {
        const r = await fetch(`${im.url}?t=${Date.now()}`, { cache: "no-store" });
        if (!r.ok) return false;
        const remote = Buffer.from(await r.arrayBuffer());
        return Buffer.compare(remote, fs.readFileSync(im.file)) === 0;   // 예전 파일이 캐시된 경우 방지
      } catch { return false; }
    }));
    if (ok.every(Boolean)) { log("이미지 공개 확인 완료"); return; }
    if (Date.now() > deadline) throw new Error("이미지 URL이 제한 시간 안에 공개되지 않았습니다: " + images.filter((_, i) => !ok[i]).map((i) => i.url).join(", "));
    log(`이미지 공개 대기… (${ok.filter(Boolean).length}/${images.length})`);
    await sleep(15000);
  }
}

async function waitContainer(cfg, id, maxSec = 240) {
  const deadline = Date.now() + maxSec * 1000;
  for (;;) {
    const r = await api(cfg, "GET", id, { fields: "status_code,status" });
    if (r.status_code === "FINISHED") return;
    if (r.status_code === "ERROR" || r.status_code === "EXPIRED") throw new Error(`컨테이너 ${id} 상태 ${r.status_code}: ${r.status || ""}`);
    if (Date.now() > deadline) throw new Error(`컨테이너 ${id} 처리 시간 초과 (${r.status_code})`);
    await sleep(5000);
  }
}

async function publish(cfg, images, caption) {
  const userId = cfg.ig_user_id;
  let creationId;
  if (images.length === 1) {
    creationId = (await api(cfg, "POST", `${userId}/media`, { image_url: images[0].url, caption })).id;
    await waitContainer(cfg, creationId);
  } else {
    const children = [];
    for (const im of images) {
      const { id } = await api(cfg, "POST", `${userId}/media`, { image_url: im.url, is_carousel_item: "true" });
      log(`아이템 컨테이너 ${children.length + 1}/${images.length}: ${id}`);
      children.push(id);
    }
    for (const id of children) await waitContainer(cfg, id);
    creationId = (await api(cfg, "POST", `${userId}/media`, { media_type: "CAROUSEL", children: children.join(","), caption })).id;
    log(`캐러셀 컨테이너: ${creationId}`);
    await waitContainer(cfg, creationId);
  }
  const { id: mediaId } = await api(cfg, "POST", `${userId}/media_publish`, { creation_id: creationId });
  const media = await api(cfg, "GET", mediaId, { fields: "id,permalink,timestamp" });
  return { media_id: mediaId, permalink: media.permalink, timestamp: media.timestamp };
}

async function main() {
  const cfg = loadConfig();
  if (flag("refresh-token")) { await maybeRefreshToken(cfg, true); return; }
  if (flag("check")) {
    const me = await api(cfg, "GET", "me", { fields: "user_id,username,account_type,media_count" });
    console.log(JSON.stringify({ ok: true, ...me, config: CONFIG_PATH }, null, 2));
    return;
  }
  const dir = opt("dir"); const capPath = opt("caption");
  if (!dir || !capPath) throw new Error("--dir <카드 폴더> --caption <캡션 txt> 가 필요합니다");
  const caption = fs.readFileSync(path.resolve(ROOT, capPath), "utf8").trim();
  const stats = validateCaption(caption);
  const base = (opt("base-url", cfg.base_url) || "").replace(/\/+$/, "");
  const images = listImages(dir).map((im) => ({ ...im, url: `${base}/${im.rel}` }));
  const waitMax = Number(opt("wait-max", 600));

  if (flag("dry-run")) {
    console.log(JSON.stringify({ dry_run: true, images: images.map((i) => i.url), caption_chars: stats.len, hashtags: stats.tags, caption_head: caption.split("\n").slice(0, 2) }, null, 2));
    return;
  }
  await maybeRefreshToken(cfg);
  if (!flag("no-wait")) { waitPagesBuild(cfg, waitMax); await waitUrls(images, waitMax); }
  const result = await publish(cfg, images, caption);
  console.log(JSON.stringify({ ok: true, ...result, images: images.length, caption_chars: stats.len, hashtags: stats.tags }, null, 2));
}

main().catch((e) => { console.error(JSON.stringify({ ok: false, error: e.message })); process.exit(1); });
