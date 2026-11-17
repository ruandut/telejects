import { useEffect, useEffectEvent } from "react";

import { liveSocket, type LiveMessage } from "@/network/socket";

/**
 * Listen to a live topic while the component is mounted (see src/network/socket.ts). Pass a
 * null topic to listen to nothing. The server decides what each person may receive.
 */
export function useLive(
  topic: string | null,
  subject: number | null,
  onMessage: (message: LiveMessage) => void,
) {
  const handle = useEffectEvent(onMessage);
  useEffect(() => {
    if (topic === null) return;
    return liveSocket.subscribe(topic, subject, (message) => handle(message));
  }, [topic, subject]);
}
