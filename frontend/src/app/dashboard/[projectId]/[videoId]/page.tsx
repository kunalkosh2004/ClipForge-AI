"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import UsageBar from "@/components/UsageBar";
import { api } from "@/lib/api";

interface Clip {
  id: string;
  video_id: string;
  project_id: string;
  title: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  storage_key: string | null;
  thumbnail_storage_key: string | null;
  status: string;
  created_at: string;
}

interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

interface Video {
  id: string;
  project_id: string;
  original_filename: string;
  status: string;
  duration_seconds: number | null;
  editing_style: string | null;
  created_at: string;
}

interface Progress {
  pct: number;
  label: string;
}

interface CaptionTheme {
  style_name: string | null;
  accent: string | null;
  muted: string | null;
  outline: string | null;
  animation: string | null;
  highlight_words: string[];
}

const CLIP_STATUS_COLORS: Record<string, string> = {
  pending: "text-gray-400",
  cutting: "text-yellow-400",
  ready: "text-green-400",
  failed: "text-red-400",
};

const STAGES: Record<string, { pct: number; label: string }> = {
  metadata_extraction: { pct: 15, label: "Reading video metadata" },
  ai_analysis: { pct: 40, label: "Analyzing with AI" },
  clip_extraction: { pct: 70, label: "Extracting clips" },
  render: { pct: 88, label: "Rendering captions" },
};

function formatTime(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function Swatch({ label, color }: { label: string; color: string }) {
  return (
    <span className="flex items-center gap-2 text-gray-300">
      <span
        className="inline-block w-4 h-4 rounded border border-gray-700"
        style={{ backgroundColor: `#${color}` }}
        aria-hidden
      />
      {label}:{" "}
      <span className="text-white font-mono text-xs">{color}</span>
    </span>
  );
}

function hex6(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.replace(/^#/, "");
  return cleaned.length === 6 ? cleaned.toUpperCase() : null;
}

function parseCaptionTheme(
  blueprint: Record<string, unknown> | null
): CaptionTheme | null {
  const globalStyle =
    blueprint && typeof blueprint.global_style === "object"
      ? (blueprint.global_style as Record<string, unknown>)
      : null;
  if (!globalStyle) return null;
  const theme =
    globalStyle.subtitle_theme && typeof globalStyle.subtitle_theme === "object"
      ? (globalStyle.subtitle_theme as Record<string, unknown>)
      : {};
  const colors = Array.isArray(theme.colors) ? theme.colors : [];
  const animation =
    typeof theme.animation === "string" ? theme.animation : null;
  const wordAnimation =
    typeof theme.word_animation === "string" ? theme.word_animation : null;
  const highlights = Array.isArray(theme.highlight_words)
    ? theme.highlight_words.filter((w): w is string => typeof w === "string")
    : [];
  return {
    style_name:
      typeof globalStyle.style_name === "string"
        ? globalStyle.style_name
        : null,
    accent: hex6(colors[0]),
    muted: hex6(colors[1]),
    outline: hex6(colors[2]),
    animation: animation ?? wordAnimation,
    highlight_words: highlights,
  };
}

export default function VideoDetailPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params.projectId as string;
  const videoId = params.videoId as string;

  const [video, setVideo] = useState<Video | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [activeTab, setActiveTab] = useState<"clips" | "transcript">("clips");
  const [loading, setLoading] = useState(true);
  const [subtitles, setSubtitles] = useState("");
  const [progress, setProgress] = useState<Progress | null>(null);
  const [prompt, setPrompt] = useState("");
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [captionTheme, setCaptionTheme] = useState<CaptionTheme | null>(null);

  const streamRef = useRef<EventSource | null>(null);
  const lastPctRef = useRef(0);
  const progressRef = useRef<Progress | null>(null);

  async function loadData() {
    try {
      const [v, clipData] = await Promise.all([
        api.getVideo(videoId),
        api.listClips(videoId),
      ]);
      setVideo(v);
      setClips(clipData.items);
      setPrompt(v.editing_style ?? "");

      if (v.status === "ready" || v.status === "processing" || v.status === "analyzing") {
        try {
          const t = await api.getTranscript(videoId);
          setTranscript(t.segments);
        } catch {
          /* no transcript yet */
        }
      }

      if (v.status === "ready" || v.status === "processing" || v.status === "analyzing") {
        try {
          const analysis = await api.getAnalysis(videoId);
          setCaptionTheme(parseCaptionTheme(analysis.editing_blueprint));
        } catch {
          setCaptionTheme(null);
        }
      }

      if (v.status === "ready" || v.status === "failed") {
        lastPctRef.current = 0;
        setProgress(null);
      } else if (v.status === "processing" || v.status === "analyzing") {
        startStreaming();
      }
    } catch {
      router.push("/dashboard");
    } finally {
      setLoading(false);
    }
  }

  function startStreaming() {
    if (streamRef.current) return;
    if (!progressRef.current) {
      progressRef.current = { pct: Math.max(lastPctRef.current, 5), label: "Processing..." };
      setProgress(progressRef.current);
    }
    const es = api.subscribeStatus(
      videoId,
      (data) => {
        const stage = STAGES[data.stage || ""];
        if (stage) {
          const pct = Math.max(lastPctRef.current, stage.pct);
          lastPctRef.current = pct;
          progressRef.current = { pct, label: data.message || stage.label };
        } else if (data.message || data.status) {
          const pct = Math.max(lastPctRef.current, 10);
          lastPctRef.current = pct;
          progressRef.current = { pct, label: `${data.message || data.status}` };
        } else {
          return;
        }
        setProgress(progressRef.current);
      },
      () => {
        streamRef.current = null;
        loadData();
      }
    );
    streamRef.current = es;
  }

  const handleSavePrompt = async () => {
    if (!video) return;
    setSavingPrompt(true);
    try {
      const updated = await api.updateVideoStyle(video.id, prompt || null);
      setVideo(updated);
      setPrompt(updated.editing_style ?? "");
    } catch {
      alert("Failed to save prompt");
    } finally {
      setSavingPrompt(false);
    }
  };

  const handleProcess = async () => {
    if (!video) return;
    setProcessing(true);
    try {
      if (prompt.trim() !== (video.editing_style ?? "")) {
        const updated = await api.updateVideoStyle(video.id, prompt || null);
        setVideo(updated);
      }
      await api.processVideo(video.id);
      setVideo((prev) =>
        prev ? { ...prev, status: "processing" } : prev
      );
      startStreaming();
    } catch {
      alert("Failed to start processing. Try again.");
      setProcessing(false);
    }
  };

  useEffect(() => {
    if (!api.isAuthenticated()) {
      router.push("/login");
      return;
    }
    const t = setTimeout(loadData, 0);
    return () => {
      clearTimeout(t);
      if (streamRef.current) {
        streamRef.current.close();
        streamRef.current = null;
        api.closeStatusStream();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, videoId]);

  const handleDownload = async (clipId: string) => {
    try {
      const { download_url } = await api.getClipDownloadUrl(clipId);
      window.open(download_url, "_blank");
    } catch {
      /* ignore */
    }
  };

  const handleDownloadSubtitles = async (format: "srt" | "vtt") => {
    try {
      const content = await api.getSubtitles(videoId, format);
      const blob = new Blob([content], {
        type: format === "srt" ? "application/x-subrip" : "text/vtt",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `subtitles.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("No subtitles available yet");
    }
  };

  const handleDeleteClip = async (clipId: string) => {
    if (!confirm("Delete this clip?")) return;
    try {
      await api.deleteClip(clipId);
      setClips((prev) => prev.filter((c) => c.id !== clipId));
    } catch {
      /* ignore */
    }
  };

  if (loading || !video) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-4">
          <Link
            href={`/dashboard/${projectId}`}
            className="text-gray-400 hover:text-white transition"
          >
            ← Back
          </Link>
          <h1 className="text-xl font-bold text-white flex-1 truncate">
            {video.original_filename}
          </h1>
          <UsageBar />
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {progress && (
          <div className="bg-purple-500/10 border border-purple-500/30 text-purple-400 rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
              <span className="text-sm">{progress.label}</span>
              <span className="ml-auto text-sm font-medium">{progress.pct}%</span>
            </div>
            <div className="mt-3 h-2 bg-purple-500/20 rounded-full overflow-hidden">
              <div
                className="h-full bg-purple-500 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress.pct}%` }}
              />
            </div>
          </div>
        )}

        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-500">Status</p>
            <p
              className={`text-lg font-medium ${
                video.status === "ready"
                  ? "text-green-400"
                  : video.status === "failed"
                  ? "text-red-400"
                  : "text-yellow-400"
              }`}
            >
              {video.status}
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-500">Duration</p>
            <p className="text-lg font-medium text-white">
              {video.duration_seconds
                ? formatTime(video.duration_seconds)
                : "—"}
            </p>
          </div>
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <p className="text-sm text-gray-500">Clips</p>
            <p className="text-lg font-medium text-white">{clips.length}</p>
          </div>
        </div>

        {captionTheme && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <p className="text-sm font-medium text-gray-400">Caption theme</p>
              {captionTheme.style_name && (
                <span className="text-xs text-purple-400 bg-purple-500/10 border border-purple-500/20 rounded-full px-2 py-0.5">
                  {captionTheme.style_name}
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-4 text-sm">
              {captionTheme.accent && (
                <Swatch label="Accent" color={captionTheme.accent} />
              )}
              {captionTheme.muted && (
                <Swatch label="Muted" color={captionTheme.muted} />
              )}
              {captionTheme.outline && (
                <Swatch label="Outline" color={captionTheme.outline} />
              )}
              {captionTheme.animation && (
                <span className="text-gray-300">
                  Animation:{" "}
                  <span className="text-white font-medium">
                    {captionTheme.animation}
                  </span>
                </span>
              )}
              {captionTheme.highlight_words.length > 0 && (
                <span className="text-gray-300">
                  Emphasis:{" "}
                  <span className="text-white font-medium">
                    {captionTheme.highlight_words.join(", ")}
                  </span>
                </span>
              )}
            </div>
          </div>
        )}

        {(video.status === "uploaded" || video.status === "failed") && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
            <label
              htmlFor="video-prompt"
              className="block text-sm font-medium text-gray-400 mb-2"
            >
              Prompt (optional)
            </label>
            <textarea
              id="video-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={2}
              placeholder="e.g. Fast-paced meme editing with zoom punches on key words, 🔥 emoji reactions, a 'Subscribe' CTA, upbeat music and whoosh sound effects"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 resize-none mb-3"
            />
            <div className="flex items-center gap-3">
              <button
                onClick={handleSavePrompt}
                disabled={savingPrompt || processing}
                className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-2 rounded-lg transition disabled:opacity-50"
              >
                {savingPrompt ? "Saving..." : "Save prompt"}
              </button>
              <button
                onClick={handleProcess}
                disabled={savingPrompt || processing}
                className="text-sm bg-green-600 hover:bg-green-700 text-white px-5 py-2 rounded-lg transition disabled:opacity-50"
              >
                {processing ? "Starting..." : "Process video"}
              </button>
            </div>
          </div>
        )}

        <div className="flex gap-4 mb-6">
          <button
            onClick={() => handleDownloadSubtitles("srt")}
            className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-2 rounded-lg transition"
          >
            Download SRT
          </button>
          <button
            onClick={() => handleDownloadSubtitles("vtt")}
            className="text-sm bg-gray-800 hover:bg-gray-700 text-gray-300 px-4 py-2 rounded-lg transition"
          >
            Download VTT
          </button>
        </div>

        <div className="flex gap-1 border-b border-gray-800 mb-6">
          <button
            onClick={() => setActiveTab("clips")}
            className={`px-4 py-3 text-sm font-medium transition ${
              activeTab === "clips"
                ? "text-white border-b-2 border-blue-500"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            Clips ({clips.length})
          </button>
          <button
            onClick={() => setActiveTab("transcript")}
            className={`px-4 py-3 text-sm font-medium transition ${
              activeTab === "transcript"
                ? "text-white border-b-2 border-blue-500"
                : "text-gray-500 hover:text-gray-300"
            }`}
          >
            Transcript ({transcript.length})
          </button>
        </div>

        {activeTab === "clips" && (
          <div className="grid gap-4">
            {clips.length === 0 ? (
              <div className="text-center py-16 text-gray-500">
                <p>No clips generated yet</p>
                <p className="text-sm mt-1">
                  Clips are created automatically during processing
                </p>
              </div>
            ) : (
              clips.map((clip) => (
                <div
                  key={clip.id}
                  className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-white font-medium truncate">
                        {clip.title || `Clip ${formatTime(clip.start_seconds)}`}
                      </h3>
                      <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
                        <span>
                          {formatTime(clip.start_seconds)} →{" "}
                          {formatTime(clip.end_seconds)}
                        </span>
                        <span>{clip.duration_seconds.toFixed(1)}s</span>
                        <span
                          className={
                            CLIP_STATUS_COLORS[clip.status] || "text-gray-400"
                          }
                        >
                          {clip.status}
                        </span>
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
                      {clip.status === "ready" && (
                        <button
                          onClick={() => handleDownload(clip.id)}
                          className="text-sm bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg transition"
                        >
                          Download
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteClip(clip.id)}
                        className="text-sm text-gray-600 hover:text-red-400 transition"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {activeTab === "transcript" && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 max-h-[600px] overflow-y-auto">
            {transcript.length === 0 ? (
              <div className="text-center py-16 text-gray-500">
                <p>No transcript available yet</p>
              </div>
            ) : (
              <div className="space-y-3">
                {transcript.map((seg, i) => (
                  <div key={i} className="flex gap-4">
                    <span className="text-xs text-gray-600 font-mono w-16 shrink-0 pt-0.5">
                      {formatTime(seg.start)}
                    </span>
                    <p className="text-sm text-gray-300">{seg.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
