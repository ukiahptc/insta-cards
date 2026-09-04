#!/usr/bin/env node
/**
 * get_token.mjs — Instagram 비즈니스 로그인(OAuth) 인증 코드 → 장기 토큰 교환, 설정 파일에 저장.
 *
 * 준비: ~/.config/insta-agent/config.json 에 app_id(Instagram 앱 ID), app_secret(Instagram 앱 시크릿 코드), redirect_uri 를 채운다.
 *   node tools/get_token.mjs --url            # 폰에서 열 인증 주소 출력
 *   node tools/get_token.mjs <인증코드>        # 코드 → 단기 토큰 → 장기 토큰(60일) → config 저장
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

const CONFIG_PATH = process.env.INSTA_AGENT_CONFIG || path.join(os.homedir(), ".config/insta-agent/config.json");
const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
const SCOPE = "instagram_business_basic,instagram_business_content_publish";
for (const k of ["app_id", "app_secret", "redirect_uri"]) {
  if (!cfg[k] || String(cfg[k]).includes("여기에")) { console.error(`설정값 ${k} 가 비어 있습니다 (${CONFIG_PATH})`); process.exit(1); }
}

const arg = process.argv[2];
if (!arg || arg === "--url") {
  const u = new URL("https://www.instagram.com/oauth/authorize");
  u.search = new URLSearchParams({ client_id: cfg.app_id, redirect_uri: cfg.redirect_uri, response_type: "code", scope: SCOPE }).toString();
  console.log(u.toString());
  process.exit(0);
}

const code = arg.replace(/#_$/, "").trim();
const r1 = await fetch("https://api.instagram.com/oauth/access_token", {
  method: "POST",
  body: new URLSearchParams({ client_id: cfg.app_id, client_secret: cfg.app_secret, grant_type: "authorization_code", redirect_uri: cfg.redirect_uri, code }),
});
const j1 = await r1.json();
if (!r1.ok || !j1.access_token) { console.error("단기 토큰 교환 실패:", JSON.stringify(j1)); process.exit(1); }

const u2 = new URL("https://graph.instagram.com/access_token");
u2.search = new URLSearchParams({ grant_type: "ig_exchange_token", client_secret: cfg.app_secret, access_token: j1.access_token }).toString();
const r2 = await fetch(u2); const j2 = await r2.json();
if (!r2.ok || !j2.access_token) { console.error("장기 토큰 교환 실패:", JSON.stringify(j2)); process.exit(1); }

const u3 = new URL("https://graph.instagram.com/v26.0/me");
u3.search = new URLSearchParams({ fields: "user_id,username,account_type", access_token: j2.access_token }).toString();
const me = await (await fetch(u3)).json();
if (!me.user_id) { console.error("계정 조회 실패:", JSON.stringify(me)); process.exit(1); }

cfg.access_token = j2.access_token;
cfg.ig_user_id = String(me.user_id);
cfg.handle ||= "@" + me.username;
cfg.token_updated_at = new Date().toISOString();
fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + "\n", { mode: 0o600 });
console.log(JSON.stringify({ ok: true, username: me.username, account_type: me.account_type, ig_user_id: cfg.ig_user_id, expires_in_days: Math.round(j2.expires_in / 86400), saved: CONFIG_PATH }, null, 2));
