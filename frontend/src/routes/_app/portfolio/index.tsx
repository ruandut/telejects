import { createFileRoute } from "@tanstack/react-router";

import { NoAccess } from "@/components/no-access";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/features/auth/api";
import { Dashboards } from "@/features/analytics/components/dashboards";
import { PortfolioView } from "@/features/analytics/components/portfolio";
import { usePermission } from "@/features/realms/permissions";

export const Route = createFileRoute("/_app/portfolio/")({
  component: PortfolioPage,
});

function PortfolioPage() {
  const me = useMe();
  const canUse = usePermission("projects.view");
  const canChange = usePermission("projects.manage");
  if (me.data && !canUse) return <NoAccess section="the Portfolio" />;
  return (
    <div className="mx-auto w-full max-w-7xl p-4 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Portfolio</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every project you can see, and charts across them.
      </p>
      <Tabs defaultValue="overview" className="mt-5">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="dashboards">Dashboards</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="mt-4">
          <PortfolioView />
        </TabsContent>
        <TabsContent value="dashboards" className="mt-4">
          <Dashboards project={null} canChange={canChange} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
