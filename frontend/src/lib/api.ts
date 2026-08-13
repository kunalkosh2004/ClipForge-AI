const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiError {
  error: { code: string; message: string; request_id?: string };
}

class ApiClient {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private statusStream: EventSource | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      this.accessToken = localStorage.getItem("access_token");
      this.refreshToken = localStorage.getItem("refresh_token");
    }
  }

  setTokens(access: string, refresh: string) {
    this.accessToken = access;
    this.refreshToken = refresh;
    if (typeof window !== "undefined") {
      localStorage.setItem("access_token", access);
      localStorage.setItem("refresh_token", refresh);
    }
  }

  clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  }

  isAuthenticated(): boolean {
    return !!this.accessToken;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }

    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    if (res.status === 401 && this.refreshToken) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        headers["Authorization"] = `Bearer ${this.accessToken}`;
        const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (!retry.ok) {
          const err: ApiError = await retry.json().catch(() => ({
            error: { code: "unknown", message: retry.statusText },
          }));
          throw err;
        }
        return retry.json();
      }
      this.clearTokens();
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw new Error("Session expired");
    }

    if (!res.ok) {
      if (res.status === 204) return undefined as T;
      const err: ApiError = await res.json().catch(() => ({
        error: { code: "unknown", message: res.statusText },
      }));
      throw err;
    }

    if (res.status === 204) return undefined as T;
    return res.json();
  }

  private async tryRefresh(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      this.setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    }
  }

  // Auth
  async register(email: string, password: string, fullName?: string) {
    const data = await this.request<{
      access_token: string;
      refresh_token: string;
      expires_in: number;
    }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
    this.setTokens(data.access_token, data.refresh_token);
    return data;
  }

  async login(email: string, password: string) {
    const data = await this.request<{
      access_token: string;
      refresh_token: string;
      expires_in: number;
    }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    this.setTokens(data.access_token, data.refresh_token);
    return data;
  }

  async getMe() {
    return this.request<{
      id: string;
      email: string;
      full_name: string | null;
      role: string;
      is_active: boolean;
      created_at: string;
    }>("/api/v1/auth/me");
  }

  // Projects
  async listProjects(limit = 20, offset = 0) {
    return this.request<{
      items: Array<{
        id: string;
        name: string;
        status: string;
        created_at: string;
      }>;
      total: number;
      limit: number;
      offset: number;
      has_more: boolean;
    }>(`/api/v1/projects?limit=${limit}&offset=${offset}`);
  }

  async createProject(name: string) {
    return this.request<{
      id: string;
      name: string;
      status: string;
      created_at: string;
    }>("/api/v1/projects", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  async deleteProject(id: string) {
    await this.request<void>(`/api/v1/projects/${id}`, { method: "DELETE" });
  }

  // Videos
  async listVideos(projectId: string, limit = 20, offset = 0) {
    return this.request<{
      items: Array<{
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
      }>;
      total: number;
      limit: number;
      offset: number;
      has_more: boolean;
    }>(
      `/api/v1/projects/${projectId}/videos?limit=${limit}&offset=${offset}`
    );
  }

  async startUpload(
    projectId: string,
    filename: string,
    contentType: string,
    sizeBytes: number
  ) {
    return this.request<{
      video_id: string;
      storage_key: string;
      upload_url: string;
      expires_in: number;
    }>("/api/v1/videos", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        filename,
        content_type: contentType,
        size_bytes: sizeBytes,
      }),
    });
  }

  async uploadFile(uploadUrl: string, file: File) {
    const res = await fetch(uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: file,
    });
    if (!res.ok) throw new Error("Upload failed");
  }

  async completeUpload(videoId: string) {
    return this.request<{ video_id: string; status: string }>(
      `/api/v1/videos/${videoId}/complete`,
      { method: "POST" }
    );
  }

  async getVideo(videoId: string) {
    return this.request<{
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
    }>(`/api/v1/videos/${videoId}`);
  }

  async updateVideoStyle(videoId: string, editingStyle: string | null) {
    return this.request<{
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
    }>(`/api/v1/videos/${videoId}`, {
      method: "PATCH",
      body: JSON.stringify({ editing_style: editingStyle?.trim() || null }),
    });
  }

  async processVideo(videoId: string) {
    return this.request<{ status: string }>(
      `/api/v1/videos/${videoId}/process`,
      { method: "POST" }
    );
  }

  async deleteVideo(videoId: string) {
    await this.request<void>(`/api/v1/videos/${videoId}`, { method: "DELETE" });
  }

  async importFromYouTube(projectId: string, url: string, title?: string) {
    return this.request<{ video_id: string; status: string }>(
      "/api/v1/videos/import",
      {
        method: "POST",
        body: JSON.stringify({
          project_id: projectId,
          url,
          ...(title ? { title } : {}),
        }),
      }
    );
  }

  // Clips
  async listClips(videoId: string, limit = 50, offset = 0) {
    return this.request<{
      items: Array<{
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
      }>;
      total: number;
      limit: number;
      offset: number;
      has_more: boolean;
    }>(`/api/v1/videos/${videoId}/clips?limit=${limit}&offset=${offset}`);
  }

  async getClipDownloadUrl(clipId: string) {
    return this.request<{ download_url: string }>(
      `/api/v1/clips/${clipId}/download`
    );
  }

  async deleteClip(clipId: string) {
    await this.request<void>(`/api/v1/clips/${clipId}`, { method: "DELETE" });
  }

  // Transcript / Subtitles
  async getTranscript(videoId: string) {
    return this.request<{
      id: string;
      video_id: string;
      language: string;
      segments: Array<{ start: number; end: number; text: string }>;
      words: Array<{ word: string; start: number; end: number }>;
      created_at: string;
    }>(`/api/v1/videos/${videoId}/transcript`);
  }

  async getSubtitles(videoId: string, format: "srt" | "vtt" = "srt") {
    const headers: Record<string, string> = {};
    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }
    const res = await fetch(
      `${API_BASE}/api/v1/videos/${videoId}/subtitles?format=${format}`,
      { headers }
    );
    if (!res.ok) throw new Error("Failed to fetch subtitles");
    return res.text();
  }

  // Analysis
  async getAnalysis(videoId: string) {
    return this.request<{
      id: string;
      video_id: string;
      understanding: Record<string, unknown>;
      editing_plan: Record<string, unknown>;
      editing_blueprint: Record<string, unknown> | null;
      ai_model: string;
      ai_cost_cents: number;
      created_at: string;
    }>(`/api/v1/videos/${videoId}/analysis`);
  }

  // AI usage
  async getAIUsage() {
    return this.request<{
      date: string;
      keys: Array<{
        key: string;
        model: string;
        requests: number;
        request_limit: number;
        requests_remaining: number;
        tokens_used: number;
        token_limit: number;
        tokens_remaining: number;
      }>;
      tokens_used: number;
      token_limit: number;
      tokens_remaining: number;
      requests: number;
      request_limit: number;
      requests_remaining: number;
    }>("/api/v1/ai/usage");
  }

  // Status SSE
  subscribeStatus(
    videoId: string,
    onEvent: (data: Record<string, string>) => void,
    onDone: () => void
  ): EventSource | null {
    if (typeof window === "undefined") return null;
    // Only ever keep one active stream open; replace any previous one so
    // rapid clicks/re-mounts cannot stack duplicate EventSource connections.
    this.closeStatusStream();
    const es = new EventSource(
      `${API_BASE}/api/v1/videos/${videoId}/stream?token=${encodeURIComponent(this.accessToken ?? "")}`
    );
    const finish = () => {
      if (this.statusStream !== es) return;
      this.statusStream = null;
      es.close();
      onDone();
    };
    es.addEventListener("status", (e) => {
      try {
        onEvent(JSON.parse(e.data));
      } catch {
        /* ignore */
      }
    });
    es.addEventListener("complete", finish);
    es.onerror = finish;
    this.statusStream = es;
    return es;
  }

  closeStatusStream() {
    if (this.statusStream) {
      this.statusStream.close();
      this.statusStream = null;
    }
  }
}

export const api = new ApiClient();
