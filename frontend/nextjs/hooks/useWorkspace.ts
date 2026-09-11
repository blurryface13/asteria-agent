"use client";

import { useCallback, useEffect, useState } from "react";
import { authFetch } from "@/helpers/auth";

export interface WorkspaceProject {
  id: string;
  name: string;
  workspace_path: string | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceConversation {
  id: string;
  project_id: string | null;
  title: string;
  mode: string;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export function useWorkspace() {
  const [projects, setProjects] = useState<WorkspaceProject[]>([]);
  const [conversations, setConversations] = useState<WorkspaceConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [projectsResponse, conversationsResponse] = await Promise.all([
        authFetch("/api/workspace/projects"),
        authFetch("/api/workspace/conversations"),
      ]);
      if (!projectsResponse.ok || !conversationsResponse.ok) {
        throw new Error(`workspace API error: ${projectsResponse.status}/${conversationsResponse.status}`);
      }
      const [projectsData, conversationsData] = await Promise.all([
        projectsResponse.json(),
        conversationsResponse.json(),
      ]);
      setProjects(Array.isArray(projectsData.projects) ? projectsData.projects : []);
      setConversations(
        Array.isArray(conversationsData.conversations) ? conversationsData.conversations : [],
      );
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "workspace API unavailable";
      setError(message);
      console.error("Failed to load workspace:", cause);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createProject = useCallback(
    async (name: string, workspacePath?: string | null) => {
      const response = await authFetch("/api/workspace/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, workspace_path: workspacePath || null }),
      });
      if (!response.ok) throw new Error(`create project failed: ${response.status}`);
      const project = (await response.json()) as WorkspaceProject;
      setProjects((current) => [project, ...current.filter((item) => item.id !== project.id)]);
      return project;
    },
    [],
  );

  return { projects, conversations, loading, error, refresh, createProject };
}
