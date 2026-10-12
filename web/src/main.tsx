import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";
import { useSkinStore } from "./store/skin";

const qc = new QueryClient();

function Root() {
  const skin = useSkinStore((s) => s.skin);
  React.useEffect(() => {
    document.documentElement.setAttribute("data-skin", skin);
  }, [skin]);
  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Root />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
