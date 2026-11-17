import { useNavigate } from "@tanstack/react-router";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { useConnect } from "../api";
import type { Connector } from "../types";
import { ConnectionForm } from "./connection-form";

export function ConnectDialog({
  connector,
  onClose,
}: {
  connector: Connector;
  onClose: () => void;
}) {
  const connect = useConnect();
  const navigate = useNavigate();
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Connect {connector.name}</DialogTitle>
          <DialogDescription>
            Use your company's own {connector.name} account. We test it straight away and fetch its
            products.
          </DialogDescription>
        </DialogHeader>
        <ConnectionForm
          connector={connector}
          connection={null}
          pending={connect.isPending}
          error={connect.error}
          submitLabel="Connect"
          onCancel={onClose}
          onSubmit={(name, fields) =>
            connect.mutate(
              { connector: connector.key, name, fields },
              {
                onSuccess: (connection) => {
                  onClose();
                  void navigate({
                    to: "/integrations/$connectionId",
                    params: { connectionId: String(connection.id) },
                  });
                },
              },
            )
          }
        />
      </DialogContent>
    </Dialog>
  );
}
