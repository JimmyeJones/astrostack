import React from "react";
import ReactDOM from "react-dom/client";
import { Center, Loader, MantineProvider, createTheme } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router-dom";

import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";

import { App } from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Dashboard } from "./routes/Dashboard";
import { Library } from "./routes/Library";
import { TargetView } from "./routes/Target";
import { StackView } from "./routes/Stack";
import { HistoryView } from "./routes/History";
import { EditorView } from "./routes/Editor";
import { GalleryView } from "./routes/Gallery";
import { JobsView } from "./routes/Jobs";
import { LogsView } from "./routes/Logs";
import { SettingsView } from "./routes/Settings";
import { StorageView } from "./routes/Storage";
import { SeestarView } from "./routes/Seestar";
import { CalibrationView } from "./routes/Calibration";
import { CombineView } from "./routes/Combine";
import { CompareView } from "./routes/Compare";
import { TonightView } from "./routes/Tonight";

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
      { index: true, element: <Dashboard /> },
      { path: "library", element: <Library /> },
      { path: "telescope", element: <SeestarView /> },
      { path: "storage", element: <StorageView /> },
      { path: "calibration", element: <CalibrationView /> },
      { path: "combine", element: <CombineView /> },
      { path: "gallery", element: <GalleryView /> },
      { path: "compare", element: <CompareView /> },
      { path: "tonight", element: <TonightView /> },
      { path: "targets/:safe", element: <TargetView /> },
      { path: "targets/:safe/stack", element: <StackView /> },
      { path: "targets/:safe/history", element: <HistoryView /> },
      { path: "targets/:safe/edit/:runId", element: <EditorView /> },
      { path: "sky", element: (
        <React.Suspense fallback={<Center h="60vh"><Loader /></Center>}>
          <SkyView />
        </React.Suspense>
      ) },
      { path: "jobs", element: <JobsView /> },
      { path: "logs", element: <LogsView /> },
      { path: "settings", element: <SettingsView /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <Notifications />
      <ErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ErrorBoundary>
    </MantineProvider>
  </React.StrictMode>,
);
