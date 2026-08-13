"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface KeyUsage {
  key: string;
  model: string;
  requests: number;
  request_limit: number;
  requests_remaining: number;
  tokens_used: number;
  token_limit: number;
  tokens_remaining: number;
}

interface Usage {
  date: string;
  keys: KeyUsage[];
  tokens_used: number;
  token_limit: number;
  tokens_remaining: number;
  requests: number;
  request_limit: number;
  requests_remaining: number;
}

const REFRESH_MS = 30_000;

function keyLabel(key: string): string {
  return key.replace(/^key-/, "Key ");
}

function shortModel(model: string): string {
  return model.replace(/^gemini-/, "").replace(/-flash$/, " Flash").replace(/-pro$/, " Pro");
}

function pct(used: number, limit: number): number {
  return limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
}

function barColor(p: number): string {
  if (p >= 90) return "bg-red-500";
  if (p >= 60) return "bg-amber-500";
  return "bg-blue-500";
}

export default function UsageBar() {
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.getAIUsage();
        if (!cancelled) setUsage(data);
      } catch {
        if (!cancelled) setUsage(null);
      }
    };
    load();
    const interval = setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!usage) return null;

  const tokenPct = pct(usage.tokens_used, usage.token_limit);

  return (
    <div
      className="hidden md:flex items-center gap-2 text-xs text-gray-400"
      title="Gemini token quota for today"
    >
      <div className="flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5">
        <span className="font-medium text-gray-300">AI</span>
        <div className="w-28 h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${barColor(tokenPct)}`}
            style={{ width: `${tokenPct}%` }}
          />
        </div>
        <span>
          {usage.tokens_used.toLocaleString()} / {usage.token_limit.toLocaleString()} tokens
        </span>
      </div>

      {usage.keys.map((k) => (
        <div
          key={k.key}
          className="bg-gray-900 border border-gray-800 rounded-lg px-2.5 py-1.5"
          title={`${keyLabel(k.key)} (${k.model}) — ${k.tokens_used.toLocaleString()} / ${k.token_limit.toLocaleString()} tokens today`}
        >
          <span className="text-gray-300 font-medium">{keyLabel(k.key)}</span>{" "}
          <span className="text-gray-500">{shortModel(k.model)}</span>{" "}
          <span>
            {k.requests}/{k.request_limit} calls
          </span>
          <span className="text-gray-500"> · {k.requests_remaining} left</span>
        </div>
      ))}
    </div>
  );
}
