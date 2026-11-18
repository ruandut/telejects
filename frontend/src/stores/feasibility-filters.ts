/**
 * How a feasibility run's sites are shown: how many to a page. Kept in localStorage so the
 * choice carries over to the next run; the sites themselves live in TanStack Query.
 */
import { create } from "zustand";

export const SITE_PAGE_SIZES = [20, 50, 100, 200] as const;
export type SitePageSize = (typeof SITE_PAGE_SIZES)[number];

const KEY = "feasibility-site-page-size";

function saved(): SitePageSize {
  try {
    const value = Number(localStorage.getItem(KEY));
    return SITE_PAGE_SIZES.find((size) => size === value) ?? SITE_PAGE_SIZES[0];
  } catch {
    return SITE_PAGE_SIZES[0];
  }
}

type FeasibilityFilters = {
  pageSize: SitePageSize;
  setPageSize: (pageSize: SitePageSize) => void;
};

export const useFeasibilityFilters = create<FeasibilityFilters>()((set) => ({
  pageSize: saved(),
  setPageSize: (pageSize) => {
    try {
      localStorage.setItem(KEY, String(pageSize));
    } catch {
      // Private mode or blocked storage: the choice lasts for this page only.
    }
    set({ pageSize });
  },
}));
