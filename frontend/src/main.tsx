import React from "react";
import ReactDOM from "react-dom/client";
import { Center, Loader, MantineProvider, createTheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";

import { App } from "./App";
import { Library } from "./routes/Library";
import { TargetView } from "./routes/Target";
import { StackView } from "./routes/Stack";
import { HistoryView } from "./routes/History";
import { JobsView } from "./routes/Jobs";
import { SettingsView } from "./routes/Settings";

// Lazy-load the 3D sky viewer so three.js stays out of the main bundle.
const SkyView = React.lazy(() =>
  import("./routes/Sky").then((m) => ({ default: m.SkyView })),
);

const theme = createTheme({
  primaryColor: "violet",
  defaultRadius: "md",
  fontFamily:
    "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
});

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 10_000 } },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Library /> },
      { path: "targets/:safe", element: <TargetView /> },
      { path: "targets/:safe/stack", element: <StackView /> },
      { path: "targets/:safe/history", element: <HistoryView /> },
      { path: "sky", element: (
        <React.Suspense fallback={<Center h="60vh"><Loader /></Center>}>
          <SkyView />
        </React.Suspense>
      ) },
      { path: "jobs", element: <JobsView /> },
      { path: "settings", element: <SettingsView /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
