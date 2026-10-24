"use client";

import type { Identity } from "@/lib/auth-store";

const PKCE_KEY = "clouddesk-oidc-pkce";
const STATE_KEY = "clouddesk-oidc-state";
const REDIRECT_KEY = "clouddesk-oidc-redirect";

interface OIDCLoginConfig {
  issuer: string;
  authorization_endpoint: string;
  client_id: string;
  scopes: string;
  redirect_uri: string;
  mode: string;
}

interface OIDCExchangeResponse {
  access_token: string;
  expires_in: number;
  tenant_id: string;
  tenant_slug: string;
  user_id: string;
  display_name: string;
  actor_type: string;
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((value) => {
    binary += String.fromCharCode(value);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomString(length = 64): string {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return base64Url(bytes).slice(0, length);
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return base64Url(new Uint8Array(digest));
}

export async function beginOidcLogin(): Promise<void> {
  const response = await fetch("/api/v1/auth/oidc/config");
  if (!response.ok) {
    throw new Error("OIDC 登录未配置或不可用");
  }
  const config = (await response.json()) as OIDCLoginConfig;
  const verifier = randomString(64);
  const state = randomString(32);
  const challenge = await sha256(verifier);
  const redirectUri = `${window.location.origin}/auth/callback`;
  sessionStorage.setItem(PKCE_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(REDIRECT_KEY, redirectUri);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: config.client_id,
    redirect_uri: redirectUri,
    scope: config.scopes,
    state,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  window.location.assign(`${config.authorization_endpoint}?${params.toString()}`);
}

export interface OIDCSession {
  identity: Identity;
  accessToken: string;
}

export async function completeOidcLogin(search: string): Promise<OIDCSession> {
  const params = new URLSearchParams(search);
  const code = params.get("code");
  const state = params.get("state");
  const error = params.get("error");
  if (error) {
    throw new Error(`OIDC 登录失败：${error}`);
  }
  if (!code || !state) {
    throw new Error("OIDC 回调缺少 code 或 state");
  }
  const expectedState = sessionStorage.getItem(STATE_KEY);
  const verifier = sessionStorage.getItem(PKCE_KEY);
  const redirectUri = sessionStorage.getItem(REDIRECT_KEY);
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(PKCE_KEY);
  sessionStorage.removeItem(REDIRECT_KEY);
  if (!expectedState || expectedState !== state || !verifier || !redirectUri) {
    throw new Error("OIDC state 校验失败，请重新登录");
  }

  const response = await fetch("/api/v1/auth/oidc/exchange", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      code_verifier: verifier,
      redirect_uri: redirectUri,
    }),
  });
  if (!response.ok) {
    throw new Error("OIDC 登录换取会话失败");
  }
  const payload = (await response.json()) as OIDCExchangeResponse;
  return {
    accessToken: payload.access_token,
    identity: {
      tenantId: payload.tenant_id,
      tenantSlug: payload.tenant_slug,
      userId: payload.user_id,
      userName: payload.display_name,
      actorType: payload.actor_type || "user",
    },
  };
}

