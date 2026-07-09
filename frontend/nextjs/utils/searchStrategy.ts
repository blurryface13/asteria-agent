import { SearchStrategy } from "@/types/data";

export const SEARCH_STRATEGY_RETRIEVERS: Record<SearchStrategy, string> = {
  general: "duckduckgo",
  academic: "openalex,arxiv",
  hybrid: "duckduckgo,openalex,arxiv",
};

export function getRetrieversForStrategy(strategy?: SearchStrategy, customRetrievers?: string) {
  if (customRetrievers?.trim()) {
    return customRetrievers.trim();
  }

  return SEARCH_STRATEGY_RETRIEVERS[strategy || "general"];
}
