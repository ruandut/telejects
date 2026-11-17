import { create } from "zustand";
import { persist } from "zustand/middleware";

type RealmState = {
  /** The company (realm) this tab works in, sent as X-Realm on every API call. null = the server's choice. */
  realmId: number | null;
  setRealmId: (realmId: number | null) => void;
};

/** Change it only through enterRealm() (features/realms/realm-gate.tsx), which drops the old data. */
export const useRealm = create<RealmState>()(
  persist(
    (set) => ({
      realmId: null,
      setRealmId: (realmId) => set({ realmId }),
    }),
    { name: "telejects.realm" },
  ),
);
