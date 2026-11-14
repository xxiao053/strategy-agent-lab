import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Workspace from "./Workspace";
import {savedExamples,savedImageURL,referenceExample} from './saved-examples';
import WorkbenchMedia from './WorkbenchMedia';
import "./style.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {new URLSearchParams(window.location.search).get('view')==='execution'?<App />:<Workspace examples={savedExamples} referenceExample={referenceExample} imageURL={savedImageURL} repositoryUrl={__SHOWCASE_REPOSITORY__} media={<WorkbenchMedia/>}/>}
  </React.StrictMode>,
);
