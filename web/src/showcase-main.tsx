import React from 'react';
import {createRoot} from 'react-dom/client';
import Workspace from './Workspace';
import WorkbenchMedia from './WorkbenchMedia';
import {savedExamples,savedImageURL,referenceExample} from './saved-examples';
import './style.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><Workspace staticMode examples={savedExamples} referenceExample={referenceExample} imageURL={savedImageURL} repositoryUrl={__SHOWCASE_REPOSITORY__} media={<WorkbenchMedia/>}/></React.StrictMode>);
