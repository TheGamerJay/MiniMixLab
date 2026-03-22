import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ProjectProvider } from "./contexts/ProjectContext";
import AppShell from "./components/AppShell";
import CreateWorkspace  from "./workspaces/CreateWorkspace";
import MixLabWorkspace  from "./workspaces/MixLabWorkspace";
import LibraryWorkspace from "./workspaces/LibraryWorkspace";
import ExportWorkspace  from "./workspaces/ExportWorkspace";

export default function App() {
  return (
    <BrowserRouter>
      <ProjectProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/create" replace />} />

            <Route path="/create"  element={<CreateWorkspace />} />
            <Route path="/mixlab"  element={<MixLabWorkspace />} />
            <Route path="/library" element={<LibraryWorkspace />} />
            <Route path="/export"  element={<ExportWorkspace />} />

            <Route path="*" element={<Navigate to="/create" replace />} />
          </Route>
        </Routes>
      </ProjectProvider>
    </BrowserRouter>
  );
}
