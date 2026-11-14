import Workspace from './Workspace';
import WorkbenchMedia from './WorkbenchMedia';
type Obj=Record<string,any>;
type Props={examples:Obj[];referenceExample?:Obj;repositoryUrl?:string;localMode?:boolean;imageURL?:(hash:string)=>string|undefined};
export default function Showcase({examples,referenceExample,repositoryUrl,localMode=false,imageURL}:Props){
  return <Workspace staticMode={!localMode} examples={examples} referenceExample={referenceExample} repositoryUrl={repositoryUrl} imageURL={imageURL} media={<WorkbenchMedia/>}/>;
}
