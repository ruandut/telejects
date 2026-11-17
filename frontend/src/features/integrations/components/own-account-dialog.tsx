import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { useUpdateConnection } from "../api";
import type { Connection, Connector } from "../types";
import { ConnectionForm } from "./connection-form";

/** Switch a provider from Telejects' account to the company's own (the card's override). */
export function OwnAccountDialog({
  connector,
  connection,
  onClose,
}: {
  connector: Connector;
  connection: Connection;
  onClose: () => void;
}) {
  const update = useUpdateConnection(connection.id);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Use your own {connector.name} account</DialogTitle>
          <DialogDescription>
            Runs will use your company's credentials instead of Telejects' account. We test them
            straight away and fetch the products your account offers. You can switch back later.
          </DialogDescription>
        </DialogHeader>
        <ConnectionForm
          connector={connector}
          connection={null}
          initialName={connection.name}
          pending={update.isPending}
          error={update.error}
          submitLabel="Use our account"
          onCancel={onClose}
          onSubmit={(name, fields) =>
            update.mutate(
              {
                name,
                credentials: "own",
                fields: Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== "")),
              },
              { onSuccess: onClose },
            )
          }
        />
      </DialogContent>
    </Dialog>
  );
}
