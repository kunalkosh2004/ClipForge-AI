"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import UsageBar from "@/components/UsageBar";
import { api } from "@/lib/api";

interface Video {
  id: string;
  project_id: string;
  original_filename: string;
  source_url: string | null;
  storage_key: string;
  content_type: string;
  size_bytes: number;
  checksum: string | null;
  duration_seconds: number | null;
  editing_style: string | null;
  status: string;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  uploading: "text-yellow-400",
  importing: "text-yellow-400",
  uploaded: "text-sky-400",
  processing: "text-blue-400",
  analyzing: "text-purple-400",
  ready: "text-green-400",
  failed: "text-red-400",
  pending: "text-gray-400",
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ProjectDetailPage() {
  const router = useRouter();
  const params = useParams();
  const projectId = params.projectId as string;
  const fileRef = useRef<HTMLInputElement>(null);

  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({});
  const [streamingVideo, setStreamingVideo] = useState<string | null>(null);
  const [streamStatus, setStreamStatus] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState("");

  const streamRef = useRef<EventSource | null>(null);
  const streamedVideoRef = useRef<string | null>(null);

  useEffect(() => {
    if (!api.isAuthenticated()) {
      router.push("/login");
      return;
    }
    loadVideos();
    return () => {
      if (streamRef.current) {
        streamRef.current.close();
        streamRef.current = null;
        api.closeStatusStream();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, projectId]);

  async function loadVideos() {
    try {
      const data = await api.listVideos(projectId);
      setVideos(data.items);
    } catch {
      router.push("/login");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadProgress("Requesting upload URL...");
    try {
      const { video_id, upload_url } = await api.startUpload(
        projectId,
        file.name,
        file.type || "video/mp4",
        file.size
      );
      setUploadProgress("Uploading file...");
      await api.uploadFile(upload_url, file);
      setUploadProgress("Storing video...");
      await api.completeUpload(video_id);

      const video = await api.getVideo(video_id);
      setVideos((prev) => [video, ...prev]);
      setUploadProgress("");
    } catch (err) {
      console.error("Upload failed:", err);
      setUploadProgress("Upload failed");
      setTimeout(() => setUploadProgress(""), 3000);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleProcess = async (video: Video) => {
    try {
      const draft = (promptDrafts[video.id] ?? "").trim();
      if (draft !== (video.editing_style ?? "")) {
        const updated = await api.updateVideoStyle(video.id, draft || null);
        setVideos((prev) =>
          prev.map((v) => (v.id === video.id ? updated : v))
        );
      }
      await api.processVideo(video.id);
      startStreaming(video.id);
      setVideos((prev) =>
        prev.map((v) =>
          v.id === video.id ? { ...v, status: "processing" } : v
        )
      );
    } catch (err) {
      console.error("Process failed:", err);
      alert("Failed to start processing. Try again.");
    }
  };

  function startStreaming(videoId: string) {
    if (streamRef.current && streamedVideoRef.current === videoId) return;
    streamedVideoRef.current = videoId;
    setStreamingVideo(videoId);
    setStreamStatus("Processing...");
    const es = api.subscribeStatus(
      videoId,
      (data) => {
        setStreamStatus(`${data.stage || ""}: ${data.message || data.status}`);
      },
      () => {
        streamRef.current = null;
        streamedVideoRef.current = null;
        setStreamingVideo(null);
        setStreamStatus("");
        loadVideos();
      }
    );
    streamRef.current = es;
  };

  const handleImport = async () => {
    const url = importUrl.trim();
    if (!url) return;
    setImporting(true);
    setImportError("");
    try {
      const { video_id } = await api.importFromYouTube(projectId, url);
      setImportOpen(false);
      setImportUrl("");
      startStreaming(video_id);
      const video = await api.getVideo(video_id);
      setVideos((prev) => [video, ...prev]);
    } catch (err) {
      console.error("Import failed:", err);
      setImportError("Failed to import. Check the URL and try again.");
    } finally {
      setImporting(false);
    }
  };

  const handleDelete = async (videoId: string) => {
    if (!confirm("Delete this video and its clips?")) return;
    try {
      await api.deleteVideo(videoId);
      setVideos((prev) => prev.filter((v) => v.id !== videoId));
    } catch {
      /* ignore */
    }
  };

  if (loading) {
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
            href="/dashboard"
            className="text-gray-400 hover:text-white transition"
          >
            ← Projects
          </Link>
          <h1 className="text-xl font-bold text-white flex-1">Project</h1>
          <UsageBar />
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-2xl font-semibold text-white">Videos</h2>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setImportOpen(true);
                setImportError("");
              }}
              disabled={uploading || importing}
              className="bg-gray-800 hover:bg-gray-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition disabled:opacity-50"
            >
              ⬇ Import from YouTube
            </button>
            <label>
              <input
                ref={fileRef}
                type="file"
                accept="video/*"
                onChange={handleUpload}
                className="hidden"
              />
              <span
                className={`inline-block bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition cursor-pointer ${
                  uploading ? "opacity-50 pointer-events-none" : ""
                }`}
              >
                {uploading ? "Uploading..." : "+ Upload Video"}
              </span>
            </label>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-6">
          <p className="text-sm text-gray-500">
            Videos stay stored until you click{" "}
            <span className="text-white font-medium">Process</span>. Add an
            optional prompt (editing style) for each video before processing.
          </p>
        </div>

        {importOpen && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-medium text-white">
                Import from YouTube
              </h3>
              <button
                onClick={() => setImportOpen(false)}
                className="text-gray-500 hover:text-white transition"
              >
                ✕
              </button>
            </div>
            <input
              type="url"
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !importing) handleImport();
              }}
              placeholder="https://www.youtube.com/watch?v=..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 mb-3"
            />
            {importError && (
              <p className="text-red-400 text-sm mb-3">{importError}</p>
            )}
            <button
              onClick={handleImport}
              disabled={importing || !importUrl.trim()}
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition disabled:opacity-50"
            >
              {importing ? "Importing..." : "Start Import"}
            </button>
          </div>
        )}

        {uploadProgress && (
          <div className="bg-blue-500/10 border border-blue-500/30 text-blue-400 text-sm rounded-lg p-4 mb-6">
            {uploadProgress}
          </div>
        )}

        {streamingVideo && (
          <div className="bg-purple-500/10 border border-purple-500/30 text-purple-400 text-sm rounded-lg p-4 mb-6">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-purple-400 rounded-full animate-pulse" />
              {streamStatus}
            </div>
          </div>
        )}

        {videos.length === 0 ? (
          <div className="text-center py-20 text-gray-500">
            <p className="text-lg mb-2">No videos yet</p>
            <p className="text-sm">Upload a video to get started</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {videos.map((video) => {
              const canProcess = video.status === "uploaded" || video.status === "failed";
              return (
                <div
                  key={video.id}
                  className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition"
                >
                  <div className="flex items-start justify-between">
                    <Link
                      href={`/dashboard/${projectId}/${video.id}`}
                      className="flex-1 min-w-0"
                    >
                      <h3 className="text-lg font-medium text-white truncate">
                        {video.original_filename}
                      </h3>
                      <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
                        <span>{formatSize(video.size_bytes)}</span>
                        {video.duration_seconds && (
                          <span>
                            {Math.floor(video.duration_seconds / 60)}m{" "}
                            {Math.floor(video.duration_seconds % 60)}s
                          </span>
                        )}
                        <span
                          className={
                            STATUS_COLORS[video.status] || "text-gray-400"
                          }
                        >
                          {video.status}
                        </span>
                      </div>
                    </Link>
                    <div className="flex items-center gap-2 ml-4">
                      {video.status === "processing" ||
                      video.status === "analyzing" ||
                      video.status === "importing" ? (
                        <button
                          onClick={() => startStreaming(video.id)}
                          className="text-gray-600 hover:text-blue-400 text-sm transition"
                        >
                          Track
                        </button>
                      ) : null}
                      <button
                        onClick={() => handleDelete(video.id)}
                        className="text-gray-600 hover:text-red-400 text-sm transition"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  {canProcess && (
                    <div className="flex items-center gap-3 mt-4">
                      <input
                        type="text"
                        value={promptDrafts[video.id] ?? video.editing_style ?? ""}
                        onChange={(e) =>
                          setPromptDrafts((prev) => ({
                            ...prev,
                            [video.id]: e.target.value,
                          }))
                        }
                        placeholder="Prompt (optional) — e.g. fast-paced meme edits with zoom punches"
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
                      />
                      <button
                        onClick={() => handleProcess(video)}
                        className="bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition"
                      >
                        Process
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
