// The page Notterizmus shows in its drawing window. Python drives it through window.ntz:
//   open(scene, options)  show the editor on a scene ({elements, appState, files} or null)
//   save()                the edited scene plus a PNG preview, as a JSON string
//   changed()             whether the scene differs from the one opened
//   render(scene)         a PNG preview of a scene without showing the editor
import React from "react";
import { createRoot } from "react-dom/client";
import { Excalidraw, exportToBlob, getSceneVersion, restore } from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";

// What a drawing keeps of Excalidraw's view state: only what changes how it looks.
const APP_STATE_KEYS = ["viewBackgroundColor", "gridSize", "gridStep", "gridModeEnabled"];
const PREVIEW_SCALE = 2;
const PREVIEW_PADDING = 12;

let api = null;
let openedVersion = 0;

const live = (elements) => elements.filter((e) => !e.isDeleted);

function usedFiles(elements, files) {
  const out = {};
  for (const e of elements) {
    if (e.type === "image" && e.fileId && files && files[e.fileId]) {
      out[e.fileId] = files[e.fileId];
    }
  }
  return out;
}

function keptAppState(appState) {
  const out = {};
  for (const k of APP_STATE_KEYS) {
    if (appState && appState[k] !== undefined && appState[k] !== null) {
      out[k] = appState[k];
    }
  }
  return out;
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

async function preview(elements, appState, files) {
  if (!elements.length) {
    return { png: "", width: 0, height: 0 };
  }
  let size = { width: 0, height: 0 };
  const blob = await exportToBlob({
    elements,
    files,
    appState: { ...appState, exportBackground: true, exportWithDarkMode: false, exportEmbedScene: false },
    mimeType: "image/png",
    exportPadding: PREVIEW_PADDING,
    getDimensions: (width, height) => {
      size = { width, height };
      return { width: width * PREVIEW_SCALE, height: height * PREVIEW_SCALE, scale: PREVIEW_SCALE };
    },
  });
  return { png: await blobToBase64(blob), width: size.width, height: size.height };
}

function restored(scene) {
  const s = scene || {};
  const r = restore({ elements: s.elements || [], appState: s.appState || {}, files: s.files || {} }, null, null);
  return { elements: live(r.elements), appState: keptAppState(r.appState), files: r.files || {} };
}

window.ntz = {
  // Resolves once Excalidraw is up and showing the scene: until then there is nothing
  // to save, and a save would hand back an empty drawing.
  async open(scene, options) {
    const opts = options || {};
    const data = restored(scene);
    const element = React.createElement(Excalidraw, {
      excalidrawAPI: (a) => { api = a; },
      initialData: {
        elements: data.elements,
        appState: { ...data.appState, theme: opts.dark ? "dark" : "light" },
        files: data.files,
        scrollToContent: true,
      },
      theme: opts.dark ? "dark" : "light",
      autoFocus: true,
      // The app saves the drawing itself; these would write files or open web pages.
      UIOptions: {
        canvasActions: { loadScene: false, saveToActiveFile: false, export: false, saveAsImage: false,
                         toggleTheme: false },
      },
    });
    createRoot(document.getElementById("root")).render(element);
    const started = Date.now();
    while (api === null || api.getAppState().isLoading) {
      if (Date.now() - started > 20000) {
        throw new Error("Excalidraw didn't show the drawing");
      }
      await new Promise((resolve) => setTimeout(resolve, 30));
    }
    openedVersion = getSceneVersion(live(api.getSceneElements()));
    return true;
  },

  changed() {
    return api !== null && getSceneVersion(live(api.getSceneElements())) !== openedVersion;
  },

  async save() {
    if (api === null) {
      throw new Error("the editor isn't open");
    }
    const elements = live(api.getSceneElements());
    const appState = keptAppState(api.getAppState());
    const files = usedFiles(elements, api.getFiles());
    const shot = await preview(elements, appState, files);
    return JSON.stringify({ scene: { elements, appState, files }, ...shot });
  },

  async render(scene) {
    const data = restored(scene);
    const shot = await preview(data.elements, data.appState, usedFiles(data.elements, data.files));
    return JSON.stringify(shot);
  },
};
