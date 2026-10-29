"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { PROJECT_STORAGE_KEY, resolveProjectSlug } from "@/lib/projects";
import type { ProjectListItem, ProjectsResponse } from "@/lib/types";

interface ProjectState {
  /** `null` while loading. */
  projects: ProjectListItem[] | null;
  /** The current project slug; `null` while loading or when there are no projects. */
  current: string | null;
  error: string | null;
  selectProject: (slug: string) => void;
}

const ProjectContext = createContext<ProjectState>({
  projects: null,
  current: null,
  error: null,
  selectProject: () => {},
});

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<ProjectListItem[] | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("project");
    const stored = localStorage.getItem(PROJECT_STORAGE_KEY);
    apiFetch<ProjectsResponse>("/v1/projects")
      .then((data) => {
        setProjects(data.projects);
        setCurrent(resolveProjectSlug(data.projects, [fromUrl, stored]));
      })
      .catch((err) => {
        setProjects([]);
        setError(err.message);
      });
  }, []);

  const selectProject = useCallback((slug: string) => {
    localStorage.setItem(PROJECT_STORAGE_KEY, slug);
    setCurrent(slug);
  }, []);

  return (
    <ProjectContext.Provider value={{ projects, current, error, selectProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject(): ProjectState {
  return useContext(ProjectContext);
}
