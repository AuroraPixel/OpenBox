// Sandbox container client — platform infrastructure shared by the chat
// composer (sandbox gate) and the workbench (terminal / files).
import { http } from "@/shared/api/http"
import type { ContainerInfo } from "@/shared/types/api"

export interface SandboxStatus {
  available: boolean
  container_id?: string
  container_name?: string
  status?: string
}

export const containersApi = {
  sandboxStatus: () => http.get<SandboxStatus>("/api/agent/sandbox/status"),
  list: () => http.get<{ containers: ContainerInfo[] }>("/api/containers"),
  create: (name?: string) => http.post<ContainerInfo>("/api/containers", { name }),
  imageStatus: () => http.get<{ exists: boolean; image: string }>("/api/containers/sandbox-image/status"),
  listFiles: (containerId: string, path: string) =>
    http.post<{ entries: FileListEntry[] } | FileListEntry[]>(
      `/api/containers/${containerId}/files/list`,
      { path },
    ),
}

export interface FileListEntry {
  name: string
  path: string
  is_dir: boolean
  size?: number
}

export const containerKeys = {
  all: (userId: string) => ["containers", userId] as const,
  sandbox: (userId: string) => ["sandbox-status", userId] as const,
  files: (containerId: string, path: string) => ["container-files", containerId, path] as const,
}
